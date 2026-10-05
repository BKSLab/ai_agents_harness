"""
Изменение задачи в Bitrix24 (описание, заголовок, дедлайн, приоритет, ответственный и т.п.).
Использование: python update_task.py <task_id> <fields_json>
  fields_json — JSON-объект полей tasks.task.update, например:
    {"DESCRIPTION": "новый текст"}
    {"TITLE": "Новое название", "PRIORITY": "2"}
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


def update_task(task_id: int, fields: dict) -> dict:
    webhook = os.environ.get("BITRIX_WEBHOOK", "").rstrip("/")
    if not webhook:
        raise SystemExit("Переменная окружения BITRIX_WEBHOOK не задана. Задайте её в окружении (см. README репозитория ai_agents_harness).")
    url = webhook + "/tasks.task.update"

    response = make_request(url, {"taskId": task_id, "fields": fields})
    if "error" in response:
        raise RuntimeError(f"Bitrix24 error: {response['error']} — {response.get('error_description', '')}")

    task = response.get("result", {}).get("task", {})
    task_url = f"https://biocard.bitrix24.ru/company/personal/user/169/tasks/task/view/{task_id}/"
    print(f"OK Задача #{task_id} обновлена ({', '.join(fields.keys())}): {task_url}")
    return task


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Использование: python update_task.py <task_id> \'{"DESCRIPTION": "..."}\'')
        sys.exit(1)
    update_task(int(sys.argv[1]), json.loads(sys.argv[2]))
