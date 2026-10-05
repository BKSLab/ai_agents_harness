"""Inspect managed features and probe our own hooks without running shell payloads."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

import tomlkit

from .install import (
    ROOT, agent_source_hashes, agent_targets, confined, desired_files, hook_definitions,
    hook_interpreter, hook_source_hashes, instruction_block, instruction_span,
    instruction_targets, normalized_path, read_receipt, sha, source_version,
)


def feature(status, *, installed=False, configured=False, managed=False, **details):
    return {"supported": True, "status": status, "installed": installed,
            "configured": configured, "managed": managed,
            "probe": {"status": "skipped", "reason": "configuration_check_only"}, **details}


def unsupported():
    return {"supported": False, "status": "unsupported", "installed": False, "configured": False,
            "managed": False, "probe": {"status": "skipped", "reason": "kimi_only"}}


def registered(doc, key, path):
    values = doc.get(key, [])
    if not isinstance(values, (list, tomlkit.items.Array)) or any(not isinstance(item, str) for item in values):
        raise ValueError("Invalid registration paths.")
    return normalized_path(path) in {normalized_path(item) for item in values}


def inspect_instructions(target, root):
    receipt = read_receipt(target)
    if not target.is_file():
        return feature("missing", target=str(target), managed=bool(receipt))
    if target.is_symlink():
        return feature("error", target=str(target), reason="symlink_destination")
    data = target.read_bytes()
    span = instruction_span(data)
    if span is None:
        return feature("unmanaged", target=str(target), reason="managed_block_missing")
    block = data[slice(*span)]
    current = block == instruction_block(root)
    return feature("configured" if current else "drift", installed=True, configured=current,
                   managed=bool(receipt), target=str(target), drift=[] if current else ["managed_block_changed"],
                   locally_modified=bool(receipt) and sha(block) != receipt.get("block_sha256"),
                   installed_version=receipt.get("harness_version"))


def inspect_copies(target, desired):
    receipt = read_receipt(target)
    if not target.is_dir():
        return feature("missing", target=str(target), managed=bool(receipt), missing=sorted(desired), different=[], obsolete_managed=[])
    missing, different = [], []
    for relative, expected in desired.items():
        path = confined(target, relative)
        if not path.is_file():
            missing.append(relative)
        elif path.read_bytes() != expected:
            different.append(relative)
    obsolete = [name for name in receipt.get("files", {}) if name not in desired and confined(target, name).exists()]
    configured = not (missing or different or obsolete)
    return feature("configured" if configured else "drift", installed=True, configured=configured,
                   managed=bool(receipt), target=str(target), missing=missing, different=different,
                   obsolete_managed=obsolete, installed_version=receipt.get("harness_version"))


def probe_hooks(root=ROOT):
    """Execute only fixed repository scripts; never execute a configured command or stdin command."""
    probes = {
        "protect_secrets": [("secret_read", {"command": "cat .env"}, 2),
                            ("public_example", {"command": "cat .env.example"}, 0)],
        "lint_on_edit": [("non_python_file", {"path": "synthetic-probe.txt"}, 0)],
        "git_gate": [("read_only_git", {"command": "git status"}, 0),
                     ("unmanaged_commit", {"command": "git commit -m synthetic-probe"}, 0)],
    }
    result = {}
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("BITRIX_", "GH_", "GITHUB_")) and key not in ("HARNESS_TASK", "HARNESS_TASK_ID")}
    with tempfile.TemporaryDirectory(prefix="harness-hook-probe-") as directory:
        # The unmanaged gate case must never consult the user's real task registry.
        env["HARNESS_HOME"] = str(Path(directory) / "private-state")
        for name, cases in probes.items():
            checks = []
            for label, tool_input, exit_code in cases:
                payload = {"hook_event_name": "PostToolUse" if name == "lint_on_edit" else "PreToolUse",
                           "tool_name": "Write" if name == "lint_on_edit" else "Bash", "cwd": directory,
                           "tool_input": tool_input}
                try:
                    run = subprocess.run(
                        [str(hook_interpreter(root)), "-E", "-s", "-X", "utf8", str(confined(root, f"hooks/{name}.py"))],
                        input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", errors="replace",
                        cwd=directory, env=env, timeout=12,
                    )
                    passed = run.returncode == exit_code
                    if name == "lint_on_edit":
                        output = json.loads(run.stdout)
                        passed = passed and isinstance(output, dict) and output.get("status") == "skipped" and output.get("reason") == "non_python_file"
                    elif run.stdout.strip():
                        output = json.loads(run.stdout)
                        passed = passed and isinstance(output, dict) and output.get("status") != "error"
                    checks.append({"case": label, "status": "passed" if passed else "failed", "exit_code": run.returncode})
                except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
                    checks.append({"case": label, "status": "error"})
            result[name] = {"status": "passed" if all(check["status"] == "passed" for check in checks) else "failed",
                            "checks": checks}
    return {"status": "passed" if all(value["status"] == "passed" for value in result.values()) else "failed",
            "method": "trusted_script_with_synthetic_stdin", "hooks": result,
            "limitation": "Does not prove live Kimi dispatch, managed task authorization, or sandbox arbitrary commands."}


def inspect_hooks(doc, receipt, root, *, probes=True):
    definitions = hook_definitions(root)
    entries = doc.get("hooks", [])
    if not isinstance(entries, (list, tomlkit.items.Array, tomlkit.items.AoT)) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("Invalid hook definitions.")
    found = {name: sum(dict(entry) == definition for entry in entries) == 1 for name, definition in definitions.items()}
    drift = [name for name, matched in found.items() if not matched]
    if receipt.get("hook_files") and receipt["hook_files"] != hook_source_hashes(root):
        drift.append("source_changed_since_install")
    configured = all(found.values())
    result = feature("configured" if configured and not drift else ("drift" if receipt.get("hooks") else "missing"),
                     installed=any(found.values()), configured=configured, managed=bool(receipt.get("hooks")),
                     drift=drift, configured_hooks=found, installed_version=receipt.get("hook_version"))
    if probes and configured:
        result["probe"] = probe_hooks(root)
        if result["probe"]["status"] != "passed":
            result["status"] = "error"
    else:
        result["probe"] = {"status": "skipped", "reason": "disabled" if not probes else "not_configured"}
    return result


def capabilities(root=ROOT, *, user_home=None, probes=True):
    root = Path(root)
    targets, instructions = agent_targets(user_home), instruction_targets(user_home)
    desired = desired_files(root)
    report = {"source_version": source_version(root), "agents": {}, "warnings": []}
    doc, receipt, kimi_error, active_agents = {}, {}, False, []
    try:
        if targets["kimi"].exists():
            doc = tomlkit.parse(targets["kimi"].read_text(encoding="utf-8-sig"))
        receipt = read_receipt(targets["kimi"])
    except (OSError, ValueError, TypeError):
        kimi_error = True
    for name, target in targets.items():
        active = target.parent.exists() or instructions[name].parent.exists()
        if active:
            active_agents.append(name)
        features = {}
        try:
            features["instructions"] = inspect_instructions(instructions[name], root)
        except (OSError, ValueError, TypeError):
            features["instructions"] = feature("error", reason="instructions_or_receipt_invalid")
        if name == "kimi":
            if kimi_error:
                for component in ("skills", "hooks", "agents"):
                    features[component] = feature("error", reason="config_or_receipt_invalid")
            else:
                for component, key, folder, receipt_key in (
                    ("skills", "extra_skill_dirs", "skills", "skill_dir"),
                    ("agents", "extra_agent_dirs", "agents", "agent_dir"),
                ):
                    try:
                        current = registered(doc, key, root / folder)
                        drift = []
                        if component == "agents":
                            hashes = agent_source_hashes(root)
                            if receipt.get("agent_files") and receipt["agent_files"] != hashes:
                                drift.append("source_changed_since_install")
                        features[component] = feature("configured" if current and not drift else ("drift" if receipt.get(receipt_key) else "missing"),
                            installed=current, configured=current, managed=bool(receipt.get(receipt_key)), drift=drift,
                            configured_directory_count=len(doc.get(key, [])),
                            source_version=source_version(root), registered_version=receipt.get(f"{component}_version"))
                    except (OSError, ValueError, TypeError):
                        features[component] = feature("error", reason="source_or_registration_invalid")
                try:
                    features["hooks"] = inspect_hooks(doc, receipt, root, probes=probes)
                except (OSError, ValueError, TypeError):
                    features["hooks"] = feature("error", reason="hooks_or_receipt_invalid")
        else:
            try:
                features["skills"] = inspect_copies(target, desired)
            except (OSError, ValueError, TypeError):
                features["skills"] = feature("error", reason="skills_or_receipt_invalid")
            features["hooks"], features["agents"] = unsupported(), unsupported()
        report["agents"][name] = features
        if active:
            report["warnings"].extend(f"{name}_{component}_{result['status']}" for component, result in features.items()
                                      if result["supported"] and result["status"] != "configured")
    if not active_agents:
        report["warnings"].append("no_agent_directories_found")
    report["ok"] = not report["warnings"]
    return report
