---
name: bitrix-task
description: "Создание задачи Bitrix24 по запросу пользователя или в рамках разрешённого процесса."
---

Создай задачу с описанием по контексту пользователя. В JSON передай `TITLE`, `DESCRIPTION`; поддерживаются `RESPONSIBLE_ID`, `AUDITORS`, `ACCOMPLICES`, `GROUP_ID`, `PRIORITY`, `DEADLINE`, `PARENT_ID`. Участников бери из запроса и настроенных умолчаний профиля. Имена разрешаются через профиль; неизвестные ID не выдумывай.

Перед первым вызовом прочитай [общий контракт CLI](../_shared/CONTRACT.md). Запуск: [scripts/create_task.py](scripts/create_task.py).

```text
python "<skill-dir>/scripts/create_task.py" --input "<absolute-path>/task.json" --operation-id <stable-id>
```
