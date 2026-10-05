#!/usr/bin/env python3
"""Observe a Python edit with project Ruff and bounded, explicit JSON diagnostics.

No fixes are applied. This is a fast lint signal, not test/review evidence and not
a task verification receipt. Every outcome exits 0 (Kimi PostToolUse is advisory).
"""

import json
from pathlib import Path
import shutil
import sys

if __package__:
    from ._common import InvalidPayload, emit, read_payload, run_bounded
else:
    from _common import InvalidPayload, emit, read_payload, run_bounded


def find_ruff(project):
    for directory in (".venv", "venv"):
        for relative in ("Scripts/ruff.exe", "bin/ruff"):
            candidate = project / directory / relative
            if candidate.is_file():
                return str(candidate), "project_venv"
    found = shutil.which("ruff")
    return (found, "path") if found else (None, None)


def compact_diagnostics(stdout):
    """Ruff JSON contains source/fix snippets: export only diagnostic coordinates."""
    try:
        messages = json.loads(stdout)
    except ValueError:
        return [], True
    if not isinstance(messages, list):
        return [], True
    diagnostics = []
    for message in messages[:12]:
        if not isinstance(message, dict) or not isinstance(message.get("location"), dict):
            continue
        location = message["location"]
        diagnostics.append({
            "code": str(message.get("code") or "syntax")[:24],
            "line": location.get("row"),
            "column": location.get("column"),
            "message": str(message.get("message", ""))[:240],
        })
    return diagnostics, len(messages) > 12


def inspect(payload):
    path = payload["tool_input"].get("path")
    if not isinstance(path, str) or not path or "\0" in path:
        raise InvalidPayload("invalid_path")
    if Path(path).suffix.casefold() != ".py":
        return "skipped", "non_python_file", {}
    raw_cwd = payload.get("cwd", str(Path.cwd()))
    if not isinstance(raw_cwd, str) or not raw_cwd or "\0" in raw_cwd:
        raise InvalidPayload("invalid_cwd")
    project = Path(raw_cwd).resolve()
    if not project.is_dir():
        raise InvalidPayload("invalid_cwd")
    target = (project / path).resolve()
    if not target.is_relative_to(project):
        return "skipped", "outside_project", {}
    if not target.is_file():
        return "skipped", "file_missing", {}
    ruff, source = find_ruff(project)
    if not ruff:
        return "skipped", "ruff_unavailable", {}
    details = {"engine": "ruff", "source": source, "file": target.relative_to(project).as_posix()}
    try:
        result = run_bounded(
            [ruff, "check", "--output-format=json", "--no-cache", "--", str(target)],
            cwd=project,
            timeout=20,
        )
    except OSError:
        return "error", "ruff_launch_error", details
    if result["timed_out"]:
        return "error", "ruff_timeout", details
    if result["returncode"] not in (0, 1):
        return "error", "ruff_error", {
            **details, "exit_code": result["returncode"], "diagnostics": result["stderr"][:2400],
            "diagnostics_truncated": result["truncated"] or len(result["stderr"]) > 2400,
        }
    if result["returncode"] == 0:
        return "passed", "ruff_passed", details
    diagnostics, truncated = compact_diagnostics(result["stdout"])
    return "failed", "ruff_findings", {
        **details, "diagnostics": diagnostics, "diagnostics_truncated": truncated or result["truncated"],
    }


def main() -> int:
    try:
        payload = read_payload()
        status, reason, details = inspect(payload)
        emit("lint_on_edit", status, reason, **details)
    except InvalidPayload as error:
        emit("lint_on_edit", "error", str(error), fail_open=True)
    except Exception:
        emit("lint_on_edit", "error", "internal_error", fail_open=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
