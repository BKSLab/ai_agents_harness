"""
Отправка сообщения в чат задачи Bitrix24.
Использование: python comment_task.py <task_id> <text>
"""
import io
import json
import os
import ssl
import sys
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Корпоративный self-signed CA в цепочке — проверку отключаем (внутренний портал)
_SSL_CTX = ssl._create_unverified_context()


def comment_task(task_id: int, text: str) -> None:
    webhook = os.environ.get("BITRIX_WEBHOOK", "").rstrip("/")
    if not webhook:
        raise SystemExit("Переменная окружения BITRIX_WEBHOOK не задана. Задайте её в окружении (см. README репозитория ai_agents_harness).")

    # Метод tasks.task.chat.message.send требует нового формата URL с /api/
    url = webhook.replace("/rest/", "/rest/api/", 1) + "/tasks.task.chat.message.send"
    payload = {
        "fields": {
            "taskId": task_id,
            "text": text,
        }
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

    result = response.get("result", {}).get("result", False)
    if result:
        print(f"Комментарий успешно добавлен в задачу #{task_id}")
    else:
        print(f"Неожиданный ответ: {json.dumps(response, ensure_ascii=False)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Использование: python comment_task.py <task_id> <text>")
        sys.exit(1)
    comment_task(int(sys.argv[1]), sys.argv[2])
