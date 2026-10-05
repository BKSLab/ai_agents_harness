---
name: bitrix-get-task
description: "Чтение задачи Bitrix24 по ID вместе с последними комментариями."
---

Прочитай задачу по её ID. По умолчанию загружаются последние 50 сообщений чата задачи; это не вся история. Для чтения только полей используй `--without-comments`.

Перед первым вызовом прочитай [общий контракт CLI](../_shared/CONTRACT.md). Запуск: [scripts/get_task.py](scripts/get_task.py).

```text
python "<skill-dir>/scripts/get_task.py" <task-id>
```
