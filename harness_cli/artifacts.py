"""Confined snapshots and bounded process receipts; these are not an OS sandbox."""

import hashlib
from contextvars import ContextVar
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import time

from .checks import PATTERNS, private_values, scan_bytes
from .install import atomic_write, json_bytes
from .redaction import redact_credentials

GIT_DEADLINE = ContextVar("git_gate_deadline", default=None)


def remaining_time(maximum=30):
    deadline = GIT_DEADLINE.get()
    remaining = maximum if deadline is None else min(maximum, deadline - time.monotonic())
    if remaining <= 0:
        raise ValueError("Git gate time budget exhausted; delivery is blocked.")
    return remaining


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def git(root, *args, check=True):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=remaining_time())
    if check and result.returncode:
        raise ValueError("Git command failed; inspect repository state locally.")
    output = result.stdout.decode("utf-8", errors="strict")
    return output if "\0" in output else output.rstrip("\r\n")


def project_root(path):
    path = Path(path).expanduser().resolve()
    return Path(git(path, "rev-parse", "--show-toplevel")).resolve()


def safe_relative(value):
    if not isinstance(value, str) or not value or "\\" in value or any(ord(c) < 32 for c in value):
        raise ValueError("Use a relative project path with forward slashes.")
    path = PurePosixPath(value)
    if path.is_absolute() or ":" in value or any(p.lower() in ("..", ".git") for p in path.parts):
        raise ValueError("Paths must stay inside the project and outside .git.")
    return path.as_posix()


def sensitive_path(path):
    name = PurePosixPath(path).name.lower()
    return ((name == ".env" or name.startswith(".env.")) and name != ".env.example"
            or name in ("id_rsa", "id_ed25519", "id_ecdsa", "credentials", "credentials.json"))


def inventory(root, *, inspect_contents=False):
    root = Path(root).resolve()
    output = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    names = sorted(set(output.split("\0")) - {""})
    if len(names) > 20000:
        raise ValueError("Snapshot exceeds 20,000 files; configure project ignores first.")
    indexed = index_tree(root)
    manifest, total = {}, 0
    denied = private_values() if inspect_contents else []
    for name in names:
        remaining_time()
        safe_relative(name)
        path = root / name
        components = [root.joinpath(*Path(name).parts[:i]) for i in range(1, len(Path(name).parts) + 1)]
        if (any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()) for p in components)
                or not path.resolve().is_relative_to(root)):
            raise ValueError("Snapshot refuses links outside the project or symbolic links.")
        if not path.exists():
            continue
        if not path.is_file():
            raise ValueError("Snapshot requires regular files; submodules need an explicit external check.")
        if sensitive_path(name):
            raise ValueError("Sensitive files must be outside tracked/unignored snapshot inputs.")
        size = path.stat().st_size
        total += size
        if size > 20_000_000 or total > 200_000_000:
            raise ValueError("Snapshot size limit exceeded; configure project ignores first.")
        data = path.read_bytes()
        if inspect_contents and scan_bytes(data, "snapshot", denied):
            raise ValueError("Snapshot contains a known private value; remove it from snapshot inputs.")
        mode = (indexed.get(name, {}).get("mode", "100644") if os.name == "nt"
                else "100755" if path.stat().st_mode & 0o111 else "100644")
        manifest[name] = {"sha256": hashlib.sha256(data).hexdigest(), "mode": mode}
    return manifest


def index_tree(root):
    tree = {}
    for record in git(root, "ls-files", "--stage", "-z").split("\0"):
        if not record:
            continue
        header, path = record.split("\t", 1)
        mode, blob, stage = header.split()
        if stage != "0":
            raise ValueError("Resolve Git conflicts before recording task evidence.")
        tree[path] = {"mode": mode, "blob": blob}
    return tree


def head_tree(root):
    tree = {}
    for record in git(root, "ls-tree", "-rz", "HEAD").split("\0"):
        if record:
            header, path = record.split("\t", 1)
            mode, kind, blob = header.split()
            if kind != "blob":
                raise ValueError("Submodules need an explicit external verification.")
            tree[path] = {"mode": mode, "blob": blob}
    return tree


def supported_git_attributes(root, manifest):
    """Only EOL normalization is supported; never execute arbitrary clean filters."""
    if not manifest:
        return
    paths = ("\0".join(manifest) + "\0").encode("utf-8")
    result = subprocess.run(["git", "check-attr", "-z", "--stdin", "filter", "working-tree-encoding", "ident"],
                            cwd=root, input=paths, capture_output=True, timeout=remaining_time(5))
    if result.returncode:
        raise ValueError("Cannot inspect Git content transformations.")
    fields = result.stdout.decode("utf-8").split("\0")[:-1]
    if len(fields) != len(manifest) * 9 or any(value not in ("unspecified", "unset") for value in fields[2::3]):
        raise ValueError("Managed delivery does not support clean filters, ident or working-tree encodings. "
                         "Verify the delivered representation in a separate approved workflow.")
    # check-attr renders the literal string filter=unset just like the boolean
    # -filter. Refuse configured drivers using these sentinel names as well.
    configured = subprocess.run(["git", "config", "--get-regexp", r"^filter\.(unset|unspecified)\.(clean|process)$"],
                                cwd=root, capture_output=True, timeout=remaining_time(5))
    if configured.returncode != 1:
        raise ValueError("Managed delivery does not support ambiguous Git filter sentinel names.")


def git_inventory(root, manifest):
    """Compare exact Git inputs, allowing EOL rules but refusing content rewriting."""
    if not manifest:
        return {}
    supported_git_attributes(root, manifest)
    # One process for the entire tree avoids timing out Kimi's hook on larger projects.
    # Paths have no control characters; Git accepts these C-style quoted UTF-8 names.
    paths = "".join(json.dumps(path, ensure_ascii=False) + "\n" for path in manifest).encode("utf-8")
    result = subprocess.run(["git", "hash-object", "--stdin-paths"], cwd=root,
                            input=paths, capture_output=True, timeout=remaining_time(5))
    if result.returncode:
        raise ValueError("Cannot compare canonical Git inputs.")
    blobs = result.stdout.decode("ascii").splitlines()
    if len(blobs) != len(manifest):
        raise ValueError("Incomplete Git input fingerprint.")
    return {path: {"mode": expected["mode"], "blob": blob}
            for (path, expected), blob in zip(manifest.items(), blobs, strict=True)}


def redact(text):
    data = redact_credentials(str(text)).encode("utf-8", errors="replace")
    denied = private_values()
    for value in sorted(set(denied), key=len, reverse=True):
        data = data.replace(value, b"[REDACTED]")
    for pattern in PATTERNS.values():
        data = pattern.sub(b"[REDACTED]", data)
    return data.decode("utf-8", errors="replace")


def check_private(value):
    raw = json.dumps(value, ensure_ascii=False).encode()
    if scan_bytes(raw, "task-input", private_values()):
        raise ValueError("Do not put credentials or private profile values in task instructions.")


def python_for(root):
    candidate = Path(root) / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(candidate) if candidate.is_file() else sys.executable


def run_command(argv, root, timeout, output_path, *, env=None):
    started = time.monotonic()
    # File-backed capture bounds memory. Receipts persist only a redacted, bounded excerpt.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(argv, cwd=root, env=env, stdout=stdout, stderr=stderr,
                                       start_new_session=os.name != "nt")
        except OSError:
            return {"status": "error", "exit_code": None, "duration_seconds": 0,
                    "reason": "command_unavailable", "log": None}
        status, reason = "failed", None
        try:
            while process.poll() is None:
                if any(os.fstat(stream.fileno()).st_size > 2_000_000 for stream in (stdout, stderr)):
                    reason = "output_limit"
                    raise subprocess.TimeoutExpired(argv, timeout)
                if time.monotonic() - started >= timeout:
                    raise subprocess.TimeoutExpired(argv, timeout)
                time.sleep(0.02)
            code = process.returncode
            if any(os.fstat(stream.fileno()).st_size > 2_000_000 for stream in (stdout, stderr)):
                status, reason = "error", "output_limit"
            else:
                status = "passed" if code == 0 else "failed"
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
            else:
                import signal
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.kill()
            process.wait(timeout=10)
            code, status, reason = None, "error", reason or "timeout"
        excerpt = {}
        for name, stream in (("stdout", stdout), ("stderr", stderr)):
            length = stream.seek(0, os.SEEK_END)
            stream.seek(0)
            excerpt[name] = redact(stream.read(32768).decode("utf-8", errors="replace"))
            excerpt[name + "_truncated"] = length > 32768
        atomic_write(Path(output_path), json_bytes(excerpt))
    return {"status": status, "exit_code": code, "reason": reason,
            "duration_seconds": round(time.monotonic() - started, 3), "log": str(output_path)}
