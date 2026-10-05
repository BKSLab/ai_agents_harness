#!/usr/bin/env bash
# Раскатка ai_agents_harness на новую машину.
# Запуск: bash install.sh (Git Bash на Windows, обычный bash на Linux/macOS)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$REPO_DIR/skills"

echo "== ai_agents_harness install =="
echo "Репозиторий: $REPO_DIR"

# 1. Python
if ! command -v python >/dev/null 2>&1; then
    echo "ОШИБКА: python не найден в PATH. Скрипты bitrix-* требуют Python 3.10+." >&2
    exit 1
fi
echo "OK: $(python --version 2>&1)"

# 2. Kimi Code: extra_skill_dirs -> скилы читаются прямо из репозитория
KIMI_HOME="${KIMI_CODE_HOME:-$HOME/.kimi-code}"
KIMI_CONFIG="$KIMI_HOME/config.toml"
if [ -d "$KIMI_HOME" ]; then
    if [ ! -f "$KIMI_CONFIG" ]; then
        touch "$KIMI_CONFIG"
    fi
    python - "$KIMI_CONFIG" "$SKILLS_DIR" <<'PY'
import re
import sys

config_path, skills_dir = sys.argv[1], sys.argv[2].replace("\\", "/")
with open(config_path, encoding="utf-8") as f:
    text = f.read()
if "extra_skill_dirs" in text:
    print("Kimi Code: extra_skill_dirs уже настроен в config.toml — проверь значение вручную")
    sys.exit(0)
line = f'extra_skill_dirs = ["{skills_dir}"]\n\n'
# Ключ верхнеуровневый: вставляем до первой [секции], иначе попадёт внутрь неё.
m = re.search(r"^\[", text, re.M)
text = text[: m.start()] + line + text[m.start():] if m else text + "\n" + line
with open(config_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)
print(f"Kimi Code: добавлено extra_skill_dirs = [\"{skills_dir}\"]")
PY
else
    echo "Kimi Code: ~/.kimi-code не найден, пропускаю"
fi

# 3. Claude Code / Codex: копирование скилов (после git pull запусти install.sh снова)
for home_dir in "$HOME/.claude" "$HOME/.codex"; do
    if [ -d "$home_dir" ]; then
        mkdir -p "$home_dir/skills"
        cp -r "$SKILLS_DIR/." "$home_dir/skills/"
        echo "OK: скилы скопированы в $home_dir/skills"
    else
        echo "Пропуск: $home_dir не найден"
    fi
done

# 4. Секреты
if [ -z "${BITRIX_WEBHOOK:-}" ]; then
    echo "ВНИМАНИЕ: BITRIX_WEBHOOK не задан — скилы bitrix-* работать не будут."
    echo "  Формат значения см. в .env.example, инструкция — в README.md (раздел «Секреты»)."
fi

echo "== Готово. Перезапусти агента: скилы подхватываются при старте сессии =="
