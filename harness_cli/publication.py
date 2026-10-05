"""Prepare a reviewed snapshot in a new local Git repository without old objects."""

from pathlib import Path
import os
import subprocess

from .checks import candidate_files, check, scan_history
from .install import ROOT, atomic_write


def export_public(destination, root=ROOT):
    destination = Path(destination).expanduser().resolve()
    if destination == root.resolve() or destination.is_relative_to(root.resolve()) or destination.exists():
        raise ValueError("Export destination must be a new directory outside the source repository.")
    validation = check(root)
    if not validation["ok"]:
        raise ValueError("Source validation failed. Run check and resolve findings before export.")
    files = candidate_files(root)
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Cannot export symlinks or files outside the source repository.")
    destination.mkdir(parents=True)
    count = 0
    for path in files:
        if path.is_file():
            atomic_write(destination / path.relative_to(root), path.read_bytes())
            count += 1
    commands = [
        ["init", "--initial-branch=main"],
        ["add", "--all"],
        ["-c", "user.name=Harness Maintainers", "-c", "user.email=noreply@users.noreply.github.com",
         "-c", "commit.gpgsign=false", "commit", "-m", "feat: portable agent harness with verified tools and installation"],
    ]
    for arguments in commands:
        env = {**os.environ, "GIT_AUTHOR_NAME": "Harness Maintainers", "GIT_COMMITTER_NAME": "Harness Maintainers",
               "GIT_AUTHOR_EMAIL": "noreply@users.noreply.github.com", "GIT_COMMITTER_EMAIL": "noreply@users.noreply.github.com"}
        subprocess.run(["git", *arguments], cwd=destination, env=env, capture_output=True, check=True)
    result = scan_history(destination, ["HEAD"])
    if result["findings"]:
        raise ValueError("Export history validation failed. The local export has not been published.")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=destination, text=True).strip()
    return {"ok": True, "path": str(destination), "files": count, "revision": revision,
            "commits": 1, "history_findings": 0, "published": False}
