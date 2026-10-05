"""Read-only diagnosis without configuration values or live API requests."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import tomlkit

from . import __version__
from .install import ROOT, agent_targets, desired_files, normalized_path, read_receipt


def binary_version(name):
    executable = shutil.which(name)
    if not executable and name == "kimi":
        candidate = Path.home() / ".kimi-code" / "bin" / "kimi.exe"
        executable = str(candidate) if candidate.exists() else None
    if not executable:
        return {"available": False}
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=10)
        version = re.search(r"\d+\.\d+(?:\.\d+)?(?:[-+][A-Za-z0-9.]+)?", result.stdout)
        return {"available": True, "version": version.group(0) if version else "unknown", "exit_code": result.returncode}
    except (OSError, subprocess.TimeoutExpired):
        return {"available": True, "version": "unavailable"}


def doctor(root=ROOT, *, versions=True, user_home=None):
    sys.path.insert(0, str(root / "skills" / "_shared"))
    from bitrix_config import Config, ToolError
    desired, targets = desired_files(root), agent_targets(user_home)
    report = {"harness_version": __version__, "python": sys.version.split()[0], "agents": {}, "warnings": []}
    revision = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True)
    report["git_revision"] = revision.stdout.strip() if revision.returncode == 0 else None
    report["working_tree_dirty"] = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root))
    for name, target in targets.items():
        state = {"target": str(target), "exists": target.exists()}
        if versions:
            state["cli"] = binary_version(name)
        if name == "kimi" and target.exists():
            try:
                doc = tomlkit.parse(target.read_text(encoding="utf-8-sig"))
                directories = doc.get("extra_skill_dirs", [])
                state["registered"] = normalized_path(root / "skills") in {normalized_path(p) for p in directories}
                state["configured_directory_count"] = len(directories)
                if not state["registered"]:
                    report["warnings"].append("kimi_not_registered")
            except (ValueError, TypeError):
                state["registered"] = False
                report["warnings"].append("kimi_invalid_config")
        elif name != "kimi" and target.exists():
            state["missing"] = [p for p in desired if not (target / p).is_file()]
            state["different"] = [p for p, data in desired.items() if (target / p).is_file() and (target / p).read_bytes() != data]
            receipt = read_receipt(target)
            state["managed"] = bool(receipt)
            state["obsolete_managed"] = [p for p in receipt.get("files", {}) if p not in desired and (target / p).exists()]
            if state["missing"] or state["different"] or state["obsolete_managed"]:
                report["warnings"].append(f"{name}_copy_drift")
        report["agents"][name] = state
    legacy = Path(os.environ.get("CODEX_HOME", str(Path(user_home or Path.home()) / ".codex"))) / "skills"
    report["legacy_codex_duplicates"] = [p.parent.name for p in (root / "skills").glob("*/SKILL.md")
                                         if (legacy / p.parent.name / "SKILL.md").exists()]
    if report["legacy_codex_duplicates"]:
        report["warnings"].append("legacy_codex_duplicates")
    report["environment_present"] = {key: bool(os.environ.get(key)) for key in
        ("BITRIX_PORTAL_URL", "BITRIX_WEBHOOK_USER_ID", "BITRIX_WEBHOOK_TOKEN", "BITRIX_CA_BUNDLE", "BITRIX_WEBHOOK")}
    try:
        config = Config.load()
        report["bitrix"] = {"configured": True, "timeout_seconds": config.timeout,
                            "read_retries": config.read_retries, "tls_verification": True,
                            "profile_users": len(config.profile.get("users", {})), "profile_chats": len(config.profile.get("chats", {}))}
    except ToolError as exc:
        report["bitrix"] = {"configured": False, "error_code": exc.code}
        report["warnings"].append("bitrix_not_configured_in_this_process")
    report["ok"] = not report["warnings"]
    return report
