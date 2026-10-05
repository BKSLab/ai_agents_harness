---
name: bitrix-send-chat-message
description: "Отправка сообщения в чат Bitrix24 по запросу пользователя или в рамках разрешённого процесса; комментарий к задаче выполняется через bitrix-comment-task."
---

Определи dialog ID или псевдоним чата из профиля. Для неизвестного чата уточни ID. Используй BBCode и JSON-файл с полем `text`. После подтверждённой отправки сообщи `message_id`.

Перед первым вызовом прочитай [общий контракт CLI](../_shared/CONTRACT.md). Запуск: [scripts/send_message.py](scripts/send_message.py).

```text
python "<skill-dir>/scripts/send_message.py" <chat-alias-or-id> --input "<absolute-path>/message.json" --operation-id <stable-id>
```
