---
name: bitrix-list-tasks
description: "Чтение списка задач Bitrix24 по роли пользователя и статусу."
---

Роли: `responsible`, `creator`, `accomplice`, `auditor`. Статус: `active`, число от 1 до 7 либо пропуск. Пользователь берётся из профиля; `--user` принимает ID или настроенное имя. Лимит `--limit`: 1–1000, по умолчанию 200. При `data.truncated=true` сообщи, что список неполный.

Перед первым вызовом прочитай [общий контракт CLI](../_shared/CONTRACT.md). Запуск: [scripts/list_tasks.py](scripts/list_tasks.py).

```text
python "<skill-dir>/scripts/list_tasks.py" creator active
```
