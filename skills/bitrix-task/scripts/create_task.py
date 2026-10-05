"""
Создание задачи в Bitrix24.
Использование: python create_task.py "Название задачи" "Описание задачи" [--group-id ID]
"""
import argparse
import io
import json
import os
import ssl
import sys
import urllib.request

# Принудительно UTF-8 для stdout на Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Корпоративный self-signed CA в цепочке — проверку отключаем (внутренний портал)
_SSL_CTX = ssl._create_unverified_context()


def create_task(
    title: str,
    description: str,
    responsible_id: int = 169,
    priority: str = "1",
    group_id: int | None = None,
) -> dict:
    webhook = os.environ.get("BITRIX_WEBHOOK", "").rstrip("/")
    if not webhook:
        raise SystemExit("Переменная окружения BITRIX_WEBHOOK не задана. Задайте её в окружении (см. README репозитория ai_agents_harness).")

    url = webhook + "/tasks.task.add.json"
    fields = {
        "TITLE": title,
        "DESCRIPTION": description,
        "RESPONSIBLE_ID": responsible_id,
        "CREATED_BY": 169,
        "AUDITORS": [123],
        "PRIORITY": priority,
    }
    if group_id is not None:
        fields["GROUP_ID"] = group_id

    payload = {"fields": fields}

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, context=_SSL_CTX) as resp:
        response = json.loads(resp.read().decode("utf-8"))

    task = response["result"]["task"]
    task_id = task["id"]
    actual_group_id = int(task.get("groupId") or 0)
    if group_id is not None and actual_group_id != group_id:
        raise RuntimeError(
            f"Bitrix24 создал задачу #{task_id}, но вернул groupId={actual_group_id} "
            f"вместо ожидаемого {group_id}"
        )

    task_url = f"https://biocard.bitrix24.ru/company/personal/user/{responsible_id}/tasks/task/view/{task_id}/"
    print(f"OK Задача #{task_id} создана: {task_url}")
    return {"id": task_id, "url": task_url, "group_id": actual_group_id or None}


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("ID группы должен быть положительным целым числом")
    return parsed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Создать задачу в Bitrix24")
    parser.add_argument("title", help="Название задачи")
    parser.add_argument("description", help="Описание задачи в BBCode")
    parser.add_argument(
        "--group-id",
        type=_positive_int,
        default=None,
        help="ID рабочей группы/проекта Bitrix24 (необязательно)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    create_task(
        title=args.title,
        description=args.description,
        group_id=args.group_id,
    )
