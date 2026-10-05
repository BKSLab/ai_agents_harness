"""Plan first, then back up and update only files managed by this harness."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

import tomlkit

ROOT = Path(__file__).resolve().parents[1]


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
    if data.get("owner") != "ai-agents-harness" or data.get("target") != str(target.resolve()):
        raise ValueError("Invalid installation receipt.")
    return data


def agent_targets(user_home=None):
    user_home = Path(user_home or Path.home())
    return {
        "kimi": Path(os.environ.get("KIMI_CODE_HOME", str(user_home / ".kimi-code"))) / "config.toml",
        "claude": Path(os.environ.get("CLAUDE_CONFIG_DIR", str(user_home / ".claude"))) / "skills",
        "codex": user_home / ".agents" / "skills",
    }


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
               "files": {k: sha(v) for k, v in desired.items()}}
    receipt_file = receipt_path(target)
    before = receipt_file.read_bytes() if receipt_file.exists() else None
    if before != json_bytes(receipt):
        changes.append(Change(receipt_file, before, json_bytes(receipt), "receipt"))
    return changes


def normalized_path(value):
    return os.path.normcase(str(Path(value).expanduser().resolve()))


def plan_kimi(config, source=ROOT):
    if config.is_symlink():
        raise ValueError("Kimi config is a symlink; configure its real parent using KIMI_CODE_HOME.")
    before = config.read_bytes() if config.exists() else None
    doc = tomlkit.parse(before.decode("utf-8-sig") if before is not None else "")
    directories = doc.get("extra_skill_dirs", [])
    if not isinstance(directories, (list, tomlkit.items.Array)) or any(not isinstance(p, str) for p in directories):
        raise ValueError("Kimi extra_skill_dirs must be an array of paths.")
    skill_dir = (source / "skills").resolve().as_posix()
    old = read_receipt(config)
    previous = old.get("skill_dir")
    updated = [p for p in directories if not previous or normalized_path(p) != normalized_path(previous)
               or normalized_path(p) == normalized_path(skill_dir)]
    if normalized_path(skill_dir) not in {normalized_path(p) for p in updated}:
        updated.append(skill_dir)
    if list(directories) != updated or "extra_skill_dirs" not in doc:
        doc["extra_skill_dirs"] = updated
    after = tomlkit.dumps(doc).encode("utf-8")
    # A real parse catches accidental nesting or invalid serialization before touching a live config.
    parsed = tomlkit.parse(after.decode("utf-8"))
    if skill_dir not in parsed["extra_skill_dirs"] and normalized_path(skill_dir) not in {
            normalized_path(p) for p in parsed["extra_skill_dirs"]}:
        raise ValueError("Kimi registration validation failed.")
    changes = [Change(config, before, after, "kimi-config")] if before != after else []
    record = {"owner": "ai-agents-harness", "target": str(config.resolve()), "source": str(source.resolve()), "skill_dir": skill_dir}
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


def install(agents, *, dry_run=False, replace_conflicts=False, migrate_legacy=False, source=ROOT, user_home=None):
    targets = agent_targets(user_home)
    if not agents:
        agents = [name for name, target in targets.items() if target.parent.exists()]
        if not agents:
            raise ValueError("No agent directories found. Choose --agents kimi claude codex explicitly.")
    if len(set(agents)) != len(agents) or set(agents) - targets.keys():
        raise ValueError("Choose each supported agent at most once.")
    desired = desired_files(source)
    if not any(path.endswith("/SKILL.md") for path in desired):
        raise ValueError("No skills found in the source repository.")
    plan = []
    for name in agents:
        if name == "kimi":
            plan += plan_kimi(targets[name], source)
        else:
            plan += plan_copies(targets[name], desired, replace_conflicts=replace_conflicts, source=source)
    if migrate_legacy:
        if "codex" not in agents:
            raise ValueError("Legacy migration requires the codex target.")
        plan += plan_legacy_codex(source, user_home)
    if len({str(c.path.resolve()) for c in plan}) != len(plan):
        raise ValueError("Agent destinations overlap; install them separately.")
    backup = None if dry_run else apply(plan)
    return {"agents": agents, "dry_run": dry_run, "changes": len(plan),
            "actions": [{"kind": c.kind, "path": str(c.path)} for c in plan],
            "backup": str(backup) if backup else None}
