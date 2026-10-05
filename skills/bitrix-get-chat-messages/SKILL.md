---
name: bitrix-get-chat-messages
description: "Чтение последних сообщений чата Bitrix24 по dialog ID или псевдониму."
---

Используй точный dialog ID или псевдоним из профиля. Если чат неизвестен, уточни его, не подбирай ID. Второй аргумент задаёт лимит 1–50, по умолчанию 20; полученные сообщения не представляют всю историю.

Перед первым вызовом прочитай [общий контракт CLI](../_shared/CONTRACT.md). Запуск: [scripts/get_messages.py](scripts/get_messages.py).

```text
python "<skill-dir>/scripts/get_messages.py" <chat-alias-or-id> 20
```
