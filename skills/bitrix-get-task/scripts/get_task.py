"""
Получение задачи из Bitrix24 по ID (новый API) + комментарии через чат задачи.
Использование: python get_task.py <task_id>
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

STATUS_MAP = {
    "pending": "ждёт выполнения",
    "in_progress": "выполняется",
    "wait_ctrl": "ожидает контроля",
    "completed": "завершена",
    "deferred": "отложена",
}

PRIORITY_MAP = {
    "high": "высокий",
    "average": "средний",
    "low": "низкий",
}


def make_request(url: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=_SSL_CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_task(task_id: int) -> None:
    webhook = os.environ.get("BITRIX_WEBHOOK", "").rstrip("/")
    if not webhook:
        raise SystemExit("Переменная окружения BITRIX_WEBHOOK не задана. Задайте её в окружении (см. README репозитория ai_agents_harness).")

    # Новый API: /rest/api/...
    api_webhook = webhook.replace("/rest/", "/rest/api/", 1)

    # Получаем задачу
    task_url = api_webhook + "/tasks.task.get"
    response = make_request(task_url, {
        "id": task_id,
        "select": [
            "id", "title", "description", "status", "priority",
            "deadline", "parentId", "chatId",
            "responsible.name", "creator.name",
        ],
    })

    if "error" in response:
        raise RuntimeError(f"Bitrix24 error: {response['error']} — {response.get('error_description', '')}")

    task = response["result"]["item"]

    # Получаем комментарии через чат задачи
    comments = []
    chat_id = task.get("chatId")
    if chat_id:
        msg_url = webhook + "/im.dialog.messages.get"
        msg_response = make_request(msg_url, {
            "DIALOG_ID": f"chat{chat_id}",
            "LIMIT": 50,
        })
        if "result" in msg_response:
            messages = msg_response["result"].get("messages", [])
            # Фильтруем системные сообщения (author_id == 0)
            comments = [
                m for m in messages
                if m.get("author_id", 0) != 0 and m.get("text", "").strip()
            ]

    result = {
        "id": task.get("id"),
        "title": task.get("title"),
        "description": task.get("description"),
        "status": STATUS_MAP.get(task.get("status", ""), task.get("status")),
        "priority": PRIORITY_MAP.get(task.get("priority", ""), task.get("priority")),
        "deadline": task.get("deadline"),
        "parentId": task.get("parentId"),
        "responsible": task.get("responsible", {}).get("name"),
        "creator": task.get("creator", {}).get("name"),
        "comments": [
            {
                "author_id": m.get("author_id"),
                "date": m.get("date", ""),
                "text": m.get("text", ""),
            }
            for m in comments
        ],
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python get_task.py <task_id>")
        sys.exit(1)
    get_task(int(sys.argv[1]))
