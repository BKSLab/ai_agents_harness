"""
Отправка сообщения в чат Bitrix24 от имени текущего пользователя (im.message.add).
Использование: python send_message.py <dialog_id> <text>
dialog_id: chatXXX — чат/группа/проект, sgXXX — чат группы, XXX — личный чат с пользователем.
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


def send_message(dialog_id: str, text: str) -> None:
    if not WEBHOOK:
        raise SystemExit("Переменная окружения BITRIX_WEBHOOK не задана. Задайте её в окружении (см. README репозитория ai_agents_harness).")
    url = WEBHOOK + "/im.message.add"
    payload = {
        "DIALOG_ID": dialog_id,
        "MESSAGE": text,
        "SYSTEM": "N",
        "URL_PREVIEW": "N",
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

    message_id = response.get("result")
    print(f"Сообщение успешно отправлено в {dialog_id}, ID сообщения: {message_id}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Использование: python send_message.py <dialog_id> <text>")
        sys.exit(1)
    send_message(sys.argv[1], sys.argv[2])

