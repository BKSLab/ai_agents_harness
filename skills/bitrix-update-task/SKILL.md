---
name: bitrix-update-task
description: Изменяет поля задачи в Bitrix24 — описание, заголовок, дедлайн, приоритет, ответственного. Используйте когда нужно отредактировать существующую задачу (например, поправить или дополнить описание).
---

Измени поля существующей задачи в Bitrix24.

## Шаги

1. **Определи task_id** и какие поля менять (из запроса пользователя).

2. **При правке описания** — сначала при необходимости получи текущее через `bitrix-get-task`, чтобы не затереть нужное (tasks.task.update перезаписывает поле целиком).

3. **Запусти скрипт** `scripts/update_task.py`. Он принимает task_id и JSON-объект полей.

   Для простых однострочных полей — напрямую:
```bash
python "<каталог этого скила>/scripts/update_task.py" <task_id> "{\"PRIORITY\": \"2\"}"
```

   Для многострочного описания (BBCode) — запиши описание в файл и вызови через Python:
```python
import importlib.util

spec = importlib.util.spec_from_file_location(
    "update_task_mod",
    r"<каталог этого скила>/scripts/update_task.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

with open(r"<путь к файлу с описанием>", encoding="utf-8") as f:
    description = f.read()

mod.update_task(task_id=<task_id>, fields={"DESCRIPTION": description})
```

4. **Выведи пользователю** подтверждение и ссылку из вывода скрипта.

## Поля tasks.task.update (UPPERCASE)

- TITLE — название
- DESCRIPTION — описание (BBCode); ⚠️ перезаписывается целиком
- PRIORITY — 2=высокий, 1=средний, 0=низкий
- DEADLINE — крайний срок ISO 8601
- RESPONSIBLE_ID — ответственный
- ACCOMPLICES / AUDITORS — массивы ID

Пути к файлам в описании — ТОЛЬКО относительные внутри проекта (абсолютные некорректно отображаются в Битриксе).

## Требования к окружению

Скрипт требует переменную окружения `BITRIX_WEBHOOK` (webhook Bitrix24 вида `https://<портал>/rest/<user_id>/<token>/`). Если переменная не задана, скрипт завершится с ошибкой — сообщи пользователю, что нужно задать `BITRIX_WEBHOOK` (см. README репозитория ai_agents_harness). Не пытайся подобрать или захардкодить значение.
