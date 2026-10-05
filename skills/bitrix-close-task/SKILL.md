---
name: bitrix-close-task
description: "Завершение задачи Bitrix24 по запросу пользователя или в рамках разрешённого процесса."
---

Проверь номер задачи и запусти завершение. Сообщай, что задача завершена, только при `data.completed=true`. Статус 4 означает ожидание контроля: так и опиши результат.

Перед первым вызовом прочитай [общий контракт CLI](../_shared/CONTRACT.md). Запуск: [scripts/close_task.py](scripts/close_task.py).

```text
python "<skill-dir>/scripts/close_task.py" <task-id> --operation-id <stable-id>
```
