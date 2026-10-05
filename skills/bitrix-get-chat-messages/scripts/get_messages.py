"""
Получение сообщений чата Bitrix24 (im.dialog.messages.get).
Использование: python get_messages.py <dialog_id> [limit]
dialog_id: chatXXX — чат/группа/проект, sgXXX — чат группы, XXX — личный чат с пользователем.
limit: по умолчанию 20, максимум 50 (без пагинации — метод не поддерживает её для больших объёмов).
"""
import io
import json
import os
import ssl
import ssl
import sys
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


# Корпоративный self-signed CA в цепочке — проверку отключаем (внутренний портал)
_SSL_CTX = ssl._create_unverified_context()
WEBHOOK = os.environ.get("BITRIX_WEBHOOK", "").rstrip("/")

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


def get_messages(dialog_id: str, limit: int = DEFAULT_LIMIT) -> None:
    if not WEBHOOK:
        raise SystemExit("Переменная окружения BITRIX_WEBHOOK не задана. Задайте её в окружении (см. README репозитория ai_agents_harness).")
    limit = min(limit, MAX_LIMIT)
    url = WEBHOOK + "/im.dialog.messages.get"
    payload = {
        "DIALOG_ID": dialog_id,
        "LAST_ID": 0,
        "LIMIT": limit,
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=_SSL_CTX) as resp:
        response = json.loads(resp.read().decode("utf-8"))

    if "error" in response:
        raise RuntimeError(f"Bitrix24 error: {response['error']} — {response.get('error_description', '')}")

    result = response.get("result", {})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python get_messages.py <dialog_id> [limit]")
        sys.exit(1)
    dialog_id = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_LIMIT
    get_messages(dialog_id, limit)

