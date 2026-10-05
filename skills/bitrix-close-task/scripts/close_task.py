"""
Закрытие (завершение) задачи в Bitrix24 — переводит задачу в статус 5 (завершена).
Использование: python close_task.py <task_id>
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


def close_task(task_id: int) -> None:
    webhook = os.environ.get("BITRIX_WEBHOOK", "").rstrip("/")
    if not webhook:
        raise SystemExit("Переменная окружения BITRIX_WEBHOOK не задана. Задайте её в окружении (см. README репозитория ai_agents_harness).")
    url = webhook + "/tasks.task.complete"

    response = make_request(url, {"taskId": task_id})
    if "error" in response:
        raise RuntimeError(f"Bitrix24 error: {response['error']} — {response.get('error_description', '')}")

    task_url = f"https://biocard.bitrix24.ru/company/personal/user/169/tasks/task/view/{task_id}/"
    print(f"OK Задача #{task_id} завершена (закрыта): {task_url}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python close_task.py <task_id>")
        sys.exit(1)
    close_task(int(sys.argv[1]))
