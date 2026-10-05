"""
Список задач из Bitrix24 по роли пользователя 169 (постановщик/исполнитель/соисполнитель/наблюдатель).
Использование: python list_tasks.py <role> [status]
  role:   responsible | creator | accomplice | auditor   (по умолчанию responsible)
  status: число (2..7) | active (не завершённые) | пусто (все)
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

USER_ID = 169

ROLE_FILTER = {
    "responsible": "RESPONSIBLE_ID",
    "creator": "CREATED_BY",
    "accomplice": "ACCOMPLICE",
    "auditor": "AUDITOR",
}

STATUS_MAP = {
    "1": "новая",
    "2": "ждёт выполнения",
    "3": "выполняется",
    "4": "ожидает контроля",
    "5": "завершена",
    "6": "отложена",
    "7": "отклонена",
}

PRIORITY_MAP = {"0": "низкий", "1": "средний", "2": "высокий"}


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


def gf(task: dict, key: str):
    """Поле задачи — пробуем UPPER и lower регистр (legacy vs new)."""
    if key in task:
        return task[key]
    return task.get(key.lower())


def list_tasks(role: str = "responsible", status: str | None = None) -> None:
    webhook = os.environ.get("BITRIX_WEBHOOK", "").rstrip("/")
    if not webhook:
        raise SystemExit("Переменная окружения BITRIX_WEBHOOK не задана. Задайте её в окружении (см. README репозитория ai_agents_harness).")
    url = webhook + "/tasks.task.list"

    filter_field = ROLE_FILTER.get(role)
    if not filter_field:
        raise ValueError(f"Неизвестная роль: {role}. Допустимо: {', '.join(ROLE_FILTER)}")

    flt: dict = {filter_field: USER_ID}
    if status:
        if status.isdigit():
            flt["STATUS"] = status
        elif status == "active":
            flt["!STATUS"] = "5"  # исключаем завершённые

    select = ["ID", "TITLE", "STATUS", "PRIORITY", "DEADLINE", "RESPONSIBLE_ID", "CREATED_BY"]
    order = {"CREATED_DATE": "desc"}

    tasks: list[dict] = []
    start = 0
    total = None
    while True:
        response = make_request(url, {
            "filter": flt,
            "select": select,
            "order": order,
            "start": start,
        })
        if "error" in response:
            raise RuntimeError(f"Bitrix24 error: {response['error']} — {response.get('error_description', '')}")
        res = response.get("result", {})
        batch = res.get("tasks", []) if isinstance(res, dict) else res
        tasks.extend(batch)
        total = response.get("total", total)
        nxt = response.get("next")
        if nxt is None or len(tasks) >= 200:
            break
        start = nxt

    result = {
        "role": role,
        "status_filter": status,
        "count": len(tasks),
        "total": total,
        "tasks": [
            {
                "id": gf(t, "ID"),
                "title": gf(t, "TITLE"),
                "status": STATUS_MAP.get(str(gf(t, "STATUS")), gf(t, "STATUS")),
                "priority": PRIORITY_MAP.get(str(gf(t, "PRIORITY")), gf(t, "PRIORITY")),
                "deadline": gf(t, "DEADLINE"),
            }
            for t in tasks
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    role_arg = sys.argv[1] if len(sys.argv) > 1 else "responsible"
    status_arg = sys.argv[2] if len(sys.argv) > 2 else None
    list_tasks(role_arg, status_arg)
