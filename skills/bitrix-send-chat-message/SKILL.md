---
name: bitrix-send-chat-message
description: "Отправка сообщения в чат Bitrix24 через локальный скрипт. Используй, когда пользователь просит написать в известный чат."
---

# Bitrix Send Chat Message

Use this skill when the user asks to send a Bitrix24 chat message.

## Requirements

- Do not expose the webhook value.
- Message formatting must use Bitrix BBCode, not Markdown.

## Known Chats

- `BRAIN`: `chat2415`
- `Автоалёрты`: `chat38689`
- `Алерты`: `chat25331`

## Procedure

1. Resolve the chat name to `dialog_id`; if unknown, ask for the exact dialog ID.
2. Convert Markdown-style formatting to Bitrix BBCode.
3. Run:

```bash
python "<каталог этого скила>/scripts/send_message.py" <dialog_id> "<message_text>"
```

4. Report the sent message ID if the command succeeds.

## Environment

The script requires the `BITRIX_WEBHOOK` environment variable (Bitrix24 webhook like `https://<portal>/rest/<user_id>/<token>/`). If it is missing the script exits with an error — tell the user to set `BITRIX_WEBHOOK` (see the ai_agents_harness repo README). Never guess or hardcode the value.
