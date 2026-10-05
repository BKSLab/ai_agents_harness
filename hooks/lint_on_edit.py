#!/usr/bin/env python3
"""Хук Kimi Code (PostToolUse/Edit|Write): ruff по изменённому .py-файлу.

Наблюдательный хук: результат уходит в контекст агента, ничего не блокирует.
ruff отсутствует или упал — молча разрешаем (fail-open).
"""

import json
import shutil
import subprocess
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    path = (payload.get("tool_input") or {}).get("path") or ""
    if not path.endswith(".py"):
        return 0
    ruff = shutil.which("ruff")
    if not ruff:
        return 0
    try:
        result = subprocess.run(
            [ruff, "check", path],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        return 0
    if result.returncode != 0:
        print(f"ruff {path}:\n{result.stdout.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
