#!/usr/bin/env python3
"""Хук Kimi Code (PreToolUse/Bash): блокирует чтение секретных файлов через shell.

Дополнительный барьер: встроенные инструменты чтения и так отказывают,
но через Bash ограничение обходится. Только вызов, exit 0/2; при любой
ошибке разрешаем (fail-open по контракту хуков).
"""

import json
import re
import sys

PATTERNS = [
    r"(^|\s|;|&&|\|\|)(cat|type|more|less|head|tail|Get-Content|gc|copy|xcopy|cp|scp)\s+[^\n]*\.env\b",
    r"(^|\s|;|&&|\|\|)(cat|type|more|less|head|tail|Get-Content|gc|copy|xcopy|cp|scp)\s+[^\n]*(id_rsa|id_ed25519|credentials)",
    r"\.env\b[^\n]*(>|>>|curl|scp|nc\b|Invoke-WebRequest|iwr)",
]

def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    for pattern in PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            print(
                "Команда читает или отправляет файл с секретами через shell. "
                "Значения секретов агенту не нужны: используй имена переменных и .env.example.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
