---
name: bitrix-get-chat-messages
description: "Получение последних сообщений из известных чатов Bitrix24 через локальный скрипт. Используй для чтения контекста из чатов BRAIN, Автоалёрты или Алерты."
---

# Bitrix Get Chat Messages

Use this skill when the user asks to read recent messages from a Bitrix24 chat.

## Requirements

- Never print or store the webhook value.

## Known Chats

- `BRAIN`: `chat2415`
- `Автоалёрты`: `chat38689`
- `Алерты`: `chat25331`

## Procedure

1. Resolve the chat name to `dialog_id`; if unknown, ask for the exact dialog ID.
2. Use `limit` from the user request, default `20`, maximum `50`.
3. Run:

```bash
python "<каталог этого скила>/scripts/get_messages.py" <dialog_id> [limit]
```

4. Present messages in readable chronological order: author, timestamp, text. Keep only relevant service details.

## Environment

The script requires the `BITRIX_WEBHOOK` environment variable (Bitrix24 webhook like `https://<portal>/rest/<user_id>/<token>/`). If it is missing the script exits with an error — tell the user to set `BITRIX_WEBHOOK` (see the ai_agents_harness repo README). Never guess or hardcode the value.
