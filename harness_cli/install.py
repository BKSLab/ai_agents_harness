"""Plan first, then back up and update only files managed by this harness."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import tomllib

import tomlkit

ROOT = Path(__file__).resolve().parents[1]
INSTRUCTIONS_START = b"<!-- BEGIN ai-agents-harness instructions -->"
INSTRUCTIONS_END = b"<!-- END ai-agents-harness instructions -->"
COMPONENTS = ("skills", "instructions", "hooks", "agents")


def home():
    return Path(os.environ.get("HARNESS_HOME", str(Path.home() / ".agent-harness"))).expanduser().resolve()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".harness-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def confined(root, relative):
    root = root.resolve()
    path = root / relative
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        raise ValueError("Installation path escapes its configured destination or is a symlink.")
    return path


def receipt_path(target):
    return home() / "installations" / (sha(str(target.resolve()).encode())[:24] + ".json")


def read_receipt(target):
    p = receipt_path(target)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("owner") != "ai-agents-harness" or data.get("target") != str(target.resolve()):
        raise ValueError("Invalid installation receipt.")
    for key in ("files", "hook_files", "agent_files"):
        if key in data and (not isinstance(data[key], dict) or any(
            not isinstance(name, str) or not isinstance(value, str) for name, value in data[key].items()
        )):
            raise ValueError("Invalid installation receipt file metadata.")
    if "hooks" in data and (not isinstance(data["hooks"], dict) or any(
        not isinstance(name, str) or not isinstance(value, dict) for name, value in data["hooks"].items()
    )):
        raise ValueError("Invalid installation receipt hook metadata.")
    for key in ("skill_dir", "agent_dir", "block_sha256"):
        if key in data and not isinstance(data[key], str):
            raise ValueError("Invalid installation receipt component metadata.")
    return data


def agent_targets(user_home=None):
    user_home = Path(user_home or Path.home())
    return {
        "kimi": Path(os.environ.get("KIMI_CODE_HOME", str(user_home / ".kimi-code"))) / "config.toml",
        "claude": Path(os.environ.get("CLAUDE_CONFIG_DIR", str(user_home / ".claude"))) / "skills",
        "codex": user_home / ".agents" / "skills",
    }


def instruction_targets(user_home=None):
    user_home = Path(user_home or Path.home())
    return {
        "kimi": Path(os.environ.get("KIMI_CODE_HOME", str(user_home / ".kimi-code"))) / "AGENTS.md",
        "claude": Path(os.environ.get("CLAUDE_CONFIG_DIR", str(user_home / ".claude"))) / "CLAUDE.md",
        "codex": Path(os.environ.get("CODEX_HOME", str(user_home / ".codex"))) / "AGENTS.md",
    }


def source_version(source=ROOT):
    path = source / "pyproject.toml"
    if not path.is_file():
        return None
    with path.open("rb") as stream:
        return tomllib.load(stream).get("project", {}).get("version")


def instruction_block(source=ROOT):
    path = confined(source, "global/AGENTS.md")
    contents = path.read_bytes().replace(b"\r\n", b"\n").rstrip(b"\n")
    if not contents or INSTRUCTIONS_START in contents or INSTRUCTIONS_END in contents:
        raise ValueError("Global instructions must be nonempty and must not contain managed markers.")
    contents.decode("utf-8")
    return INSTRUCTIONS_START + b"\n" + contents + b"\n" + INSTRUCTIONS_END + b"\n"


def instruction_span(contents):
    """Locate only our delimited block, leaving every surrounding byte untouched."""
    starts, ends = contents.count(INSTRUCTIONS_START), contents.count(INSTRUCTIONS_END)
    if starts == ends == 0:
        return None
    if starts != 1 or ends != 1:
        raise ValueError("Global instructions contain ambiguous managed markers; repair the markers first.")
    pattern = rb"(?ms)^" + re.escape(INSTRUCTIONS_START) + rb"\r?\n.*?^" + re.escape(INSTRUCTIONS_END) + rb"(?:\r?\n|$)"
    match = re.search(pattern, contents)
    if not match:
        raise ValueError("Global instructions contain malformed managed markers; repair the markers first.")
    return match.span()


def plan_instructions(target, source=ROOT, *, replace_conflicts=False):
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError("Instructions destination must be a regular file, not a symlink.")
    before = target.read_bytes() if target.exists() else None
    block = instruction_block(source)
    receipt = read_receipt(target)
    span = instruction_span(before or b"")
    if span:
        start, end = span
        current = before[start:end]
        if current != block and sha(current) != receipt.get("block_sha256") and not replace_conflicts:
            raise ValueError("Local instructions conflicts; inspect the managed block or use --replace-conflicts with automatic backup.")
        after = before[:start] + block + before[end:]
    else:
        if receipt.get("block_sha256") and not replace_conflicts:
            raise ValueError("Managed instructions were removed locally; use --replace-conflicts to restore them.")
        prefix = before or b""
        # Adopt an exact manual copy without keeping a second copy of the same rules.
        if prefix.replace(b"\r\n", b"\n").strip() == (source / "global/AGENTS.md").read_bytes().replace(b"\r\n", b"\n").strip():
            prefix = b""
        separator = b"" if not prefix or prefix.replace(b"\r\n", b"\n").endswith(b"\n\n") else (b"\n" if prefix.endswith(b"\n") else b"\n\n")
        after = prefix + separator + block
    changes = [Change(target, before, after, "instructions")] if before != after else []
    record = {"owner": "ai-agents-harness", "target": str(target.resolve()), "source": str(source.resolve()),
              "component": "instructions", "block_sha256": sha(block), "harness_version": source_version(source)}
    path = receipt_path(target)
    previous = path.read_bytes() if path.exists() else None
    if previous != json_bytes(record):
        changes.append(Change(path, previous, json_bytes(record), "receipt"))
    return changes


def hook_interpreter(source=ROOT):
    candidate = source / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    # Preserve a venv interpreter symlink: resolving it can silently run the base environment.
    return candidate.absolute() if candidate.is_file() else Path(sys.executable).absolute()


def hook_definitions(source=ROOT):
    """Kimi invokes a shell: POSIX quoting and forward slashes also work in Git Bash."""
    python = hook_interpreter(source).as_posix()
    result = {}
    for name, event, matcher, timeout in (
        ("protect_secrets", "PreToolUse", "Bash", 5),
        ("lint_on_edit", "PostToolUse", "Edit|Write", 30),
        ("git_gate", "PreToolUse", "Bash", 10),
    ):
        script = confined(source, f"hooks/{name}.py")
        if not script.is_file():
            raise ValueError("A required hook script is missing from the source repository.")
        result[name] = {"event": event, "matcher": matcher,
                        "command": shlex.join([python, "-E", "-s", "-X", "utf8", script.resolve().as_posix()]), "timeout": timeout}
    return result


def hook_source_hashes(source=ROOT):
    hashes = {}
    for path in sorted((source / "hooks").glob("*.py")):
        path = confined(source, path.relative_to(source))
        hashes[path.name] = sha(path.read_bytes())
    return hashes


def merge_hooks(doc, receipt, source=ROOT, *, replace_conflicts=False):
    desired = hook_definitions(source)
    previous = receipt.get("hooks", {})
    entries = doc.get("hooks")
    if entries is None or isinstance(entries, (list, tomlkit.items.Array)) and not entries:
        entries = tomlkit.aot()
        doc["hooks"] = entries
    if not isinstance(entries, tomlkit.items.AoT):
        raise ValueError("Kimi hooks must use [[hooks]] tables.")
    remove = []
    for name, old in previous.items():
        matches = [index for index, entry in enumerate(entries) if entry.get("command") == old.get("command")]
        if not matches and not replace_conflicts:
            raise ValueError("Managed hook command was removed or edited locally; inspect it before using --replace-conflicts.")
        for index in matches:
            if dict(entries[index]) != old and not replace_conflicts:
                raise ValueError("Local hook conflicts; inspect them or use --replace-conflicts with automatic backup.")
            if name not in desired or dict(entries[index]) != desired[name] or len(matches) > 1:
                remove.append(index)
    for index in sorted(set(remove), reverse=True):
        del entries[index]
    for definition in desired.values():
        matching = [entry for entry in entries if entry.get("command") == definition["command"]]
        if matching:
            if len(matching) != 1 or dict(matching[0]) != definition:
                raise ValueError("An unmanaged hook uses the same command with different settings; resolve the conflict first.")
            continue
        table = tomlkit.table()
        for key, value in definition.items():
            table[key] = value
        entries.append(table)
    receipt.update({"hooks": desired, "hook_source": str(source.resolve()),
                    "hook_interpreter": str(hook_interpreter(source)), "hook_files": hook_source_hashes(source),
                    "hook_version": source_version(source)})


def desired_files(root=ROOT):
    result = {}
    for folder in sorted((root / "skills").iterdir()):
        if not folder.is_dir() or (folder.name != "_shared" and not (folder / "SKILL.md").is_file()):
            continue
        for path in sorted(folder.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                if path.is_symlink() or not path.resolve().is_relative_to((root / "skills").resolve()):
                    raise ValueError("Source skills must not contain symlinks outside their package.")
                result[path.relative_to(root / "skills").as_posix()] = path.read_bytes()
    return result


@dataclass
class Change:
    path: Path
    before: bytes | None
    after: bytes | None
    kind: str


def plan_copies(target, desired, *, replace_conflicts=False, source=ROOT):
    manifest = read_receipt(target)
    owned = manifest.get("files", {})
    changes, conflicts = [], []
    for relative, contents in desired.items():
        path = confined(target, relative)
        before = path.read_bytes() if path.is_file() else None
        if path.exists() and not path.is_file():
            raise ValueError("Expected a file at an installation destination.")
        if before == contents:
            continue
        if before is not None and sha(before) != owned.get(relative) and not replace_conflicts:
            conflicts.append(relative)
        changes.append(Change(path, before, contents, "copy"))
    for relative, old_hash in owned.items():
        if relative in desired:
            continue
        path = confined(target, relative)
        if path.is_file():
            before = path.read_bytes()
            if sha(before) != old_hash and not replace_conflicts:
                conflicts.append(relative)
            changes.append(Change(path, before, None, "remove-managed"))
    if conflicts:
        raise ValueError("Local skill conflicts; inspect them or use --replace-conflicts with automatic backup: "
                         + ", ".join(conflicts))
    receipt = {"owner": "ai-agents-harness", "target": str(target.resolve()), "source": str(source.resolve()),
               "files": {k: sha(v) for k, v in desired.items()}, "harness_version": source_version(source)}
    receipt_file = receipt_path(target)
    before = receipt_file.read_bytes() if receipt_file.exists() else None
    if before != json_bytes(receipt):
        changes.append(Change(receipt_file, before, json_bytes(receipt), "receipt"))
    return changes


def normalized_path(value):
    return os.path.normcase(str(Path(value).expanduser().resolve()))


def register_directory(doc, record, key, receipt_key, destination):
    directories = doc.get(key, [])
    if not isinstance(directories, (list, tomlkit.items.Array)) or any(not isinstance(p, str) for p in directories):
        raise ValueError(f"Kimi {key} must be an array of paths.")
    new = destination.resolve().as_posix()
    previous = record.get(receipt_key)
    updated = []
    for value in directories:
        if previous and normalized_path(value) == normalized_path(previous) and normalized_path(value) != normalized_path(new):
            continue
        if normalized_path(value) not in {normalized_path(item) for item in updated}:
            updated.append(value)
    if normalized_path(new) not in {normalized_path(item) for item in updated}:
        updated.append(new)
    if list(directories) != updated or key not in doc:
        doc[key] = updated
    record[receipt_key] = new


def agent_source_hashes(source=ROOT):
    hashes = {}
    for path in sorted((source / "agents").rglob("*.md")):
        path = confined(source, path.relative_to(source))
        hashes[path.relative_to(source / "agents").as_posix()] = sha(path.read_bytes())
    if not hashes:
        raise ValueError("No custom agent profiles found in the source repository.")
    return hashes


def plan_kimi(config, source=ROOT, *, skills=True, hooks=False, agents=False, replace_conflicts=False):
    if config.is_symlink():
        raise ValueError("Kimi config is a symlink; configure its real parent using KIMI_CODE_HOME.")
    before = config.read_bytes() if config.exists() else None
    doc = tomlkit.parse(before.decode("utf-8-sig") if before is not None else "")
    record = read_receipt(config).copy()
    if skills:
        register_directory(doc, record, "extra_skill_dirs", "skill_dir", source / "skills")
        record["skills_version"] = source_version(source)
    if agents:
        register_directory(doc, record, "extra_agent_dirs", "agent_dir", source / "agents")
        record["agent_files"] = agent_source_hashes(source)
        record["agents_version"] = source_version(source)
    if hooks:
        merge_hooks(doc, record, source, replace_conflicts=replace_conflicts)
    after = tomlkit.dumps(doc).encode("utf-8")
    # A real parse catches accidental nesting or invalid serialization before touching a live config.
    parsed = tomlkit.parse(after.decode("utf-8"))
    for enabled, key, folder in ((skills, "extra_skill_dirs", "skills"), (agents, "extra_agent_dirs", "agents")):
        if enabled and normalized_path(source / folder) not in {normalized_path(p) for p in parsed[key]}:
            raise ValueError("Kimi registration validation failed.")
    changes = [Change(config, before, after, "kimi-config")] if before != after else []
    record.update({"owner": "ai-agents-harness", "target": str(config.resolve()), "source": str(source.resolve())})
    path = receipt_path(config)
    previous_bytes = path.read_bytes() if path.exists() else None
    if previous_bytes != json_bytes(record):
        changes.append(Change(path, previous_bytes, json_bytes(record), "receipt"))
    return changes


def plan_legacy_codex(source=ROOT, user_home=None):
    """Remove committed pre-upgrade copies, allowing Git's CRLF/LF text conversion."""
    user_home = Path(user_home or Path.home())
    legacy = Path(os.environ.get("CODEX_HOME", str(user_home / ".codex"))) / "skills"
    if not legacy.exists():
        return []
    result = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD", "skills"], cwd=source,
                            capture_output=True, text=True, check=True)
    changes = []
    for name in result.stdout.splitlines():
        relative = Path(name).relative_to("skills").as_posix()
        path = confined(legacy, relative)
        if path.is_file():
            old = subprocess.check_output(["git", "show", f"HEAD:{name}"], cwd=source)
            before = path.read_bytes()
            if old != before and old.replace(b"\r\n", b"\n") != before.replace(b"\r\n", b"\n"):
                raise ValueError("Legacy Codex copy differs from the committed baseline; migration stopped.")
            changes.append(Change(path, before, None, "migrate-legacy"))
    return changes


def apply(changes):
    # Check the complete plan again before any write. Avoid overwriting edits made after planning.
    for item in changes:
        now = item.path.read_bytes() if item.path.is_file() else None
        if now != item.before:
            raise ValueError("Installation files changed after planning; rerun the installer.")
    if not changes:
        return None
    backup = home() / "backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup.mkdir(parents=True, mode=0o700)
    record = []
    for index, item in enumerate(changes):
        saved = None
        if item.before is not None:
            saved = f"{index:04d}.bak"
            atomic_write(backup / saved, item.before)
        record.append({"destination": str(item.path), "backup": saved,
                       "installed_hash": sha(item.after) if item.after is not None else None})
    atomic_write(backup / "restore.json", json_bytes(record))
    completed = []
    try:
        for item in changes:
            if item.after is None:
                item.path.unlink()
            else:
                atomic_write(item.path, item.after)
            completed.append(item)
    except BaseException:
        for item in reversed(completed):
            if item.before is None:
                item.path.unlink(missing_ok=True)
            else:
                atomic_write(item.path, item.before)
        raise
    return backup


def install(agents, *, dry_run=False, replace_conflicts=False, migrate_legacy=False, source=ROOT, user_home=None, components=None):
    source = Path(source).resolve()
    components = ["skills"] if components is None else list(components)
    if not components or len(set(components)) != len(components) or set(components) - set(COMPONENTS):
        raise ValueError("Choose each supported component at most once: skills, instructions, hooks, agents.")
    targets = agent_targets(user_home)
    instructions = instruction_targets(user_home)
    if not agents:
        agents = [name for name, target in targets.items() if target.parent.exists() or instructions[name].parent.exists()]
        if not agents:
            raise ValueError("No agent directories found. Choose --agents kimi claude codex explicitly.")
    if len(set(agents)) != len(agents) or set(agents) - targets.keys():
        raise ValueError("Choose each supported agent at most once.")
    desired = desired_files(source) if "skills" in components else {}
    if "skills" in components and not any(path.endswith("/SKILL.md") for path in desired):
        raise ValueError("No skills found in the source repository.")
    plan, unsupported = [], []
    for name in agents:
        if name == "kimi" and set(components) & {"skills", "hooks", "agents"}:
            plan += plan_kimi(targets[name], source, skills="skills" in components, hooks="hooks" in components,
                              agents="agents" in components, replace_conflicts=replace_conflicts)
        elif name != "kimi" and "skills" in components:
            plan += plan_copies(targets[name], desired, replace_conflicts=replace_conflicts, source=source)
        if "instructions" in components:
            plan += plan_instructions(instructions[name], source, replace_conflicts=replace_conflicts)
        if name != "kimi":
            unsupported.extend({"agent": name, "component": component, "reason": "kimi_only"}
                               for component in components if component in ("hooks", "agents"))
    if migrate_legacy:
        if "codex" not in agents or "skills" not in components:
            raise ValueError("Legacy migration requires the codex target and skills component.")
        plan += plan_legacy_codex(source, user_home)
    if len({str(c.path.resolve()) for c in plan}) != len(plan):
        raise ValueError("Agent destinations overlap; install them separately.")
    backup = None if dry_run else apply(plan)
    return {"agents": agents, "components": components, "unsupported": unsupported, "dry_run": dry_run, "changes": len(plan),
            "actions": [{"kind": c.kind, "path": str(c.path)} for c in plan],
            "backup": str(backup) if backup else None}
