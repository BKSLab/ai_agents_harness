---
name: bitrix-comment-task
description: "Добавление комментария в чат задачи Bitrix24 по запросу пользователя или в рамках разрешённого процесса."
---

Определи задачу и текст комментария. Используй BBCode и JSON-файл с единственным полем `text`. Подтверждение API означает добавление комментария, но не завершение самой задачи.

Перед первым вызовом прочитай [общий контракт CLI](../_shared/CONTRACT.md). Запуск: [scripts/comment_task.py](scripts/comment_task.py).

```text
python "<skill-dir>/scripts/comment_task.py" <task-id> --input "<absolute-path>/message.json" --operation-id <stable-id>
```
