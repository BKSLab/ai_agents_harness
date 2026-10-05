---
name: bitrix-update-task
description: "Изменение полей задачи Bitrix24 по запросу пользователя или в рамках разрешённого процесса."
---

Перед заменой `DESCRIPTION` прочитай текущее описание и сохрани нужные пользователю части. JSON содержит только изменяемые UPPERCASE-поля: `TITLE`, `DESCRIPTION`, `RESPONSIBLE_ID`, `PRIORITY`, `DEADLINE`, `GROUP_ID`, `PARENT_ID`, `AUDITORS`, `ACCOMPLICES`. Остальные поля не перезаписывай.

Перед первым вызовом прочитай [общий контракт CLI](../_shared/CONTRACT.md). Запуск: [scripts/update_task.py](scripts/update_task.py).

```text
python "<skill-dir>/scripts/update_task.py" <task-id> --input "<absolute-path>/fields.json" --operation-id <stable-id>
```
