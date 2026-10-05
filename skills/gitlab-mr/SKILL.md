---
name: gitlab-mr
description: "Чтение merge requests GitLab; создание, merge и approve по запросу пользователя или в рамках разрешённого процесса."
---

Проект задаётся `--project`: путь `group/project`, числовой ID или псевдоним из профиля. Действие задаётся `--action`:

- `list` — список MR; `--state`: `opened|closed|merged|locked|all`, по умолчанию `opened`; `--limit`: 1–500, по умолчанию 100. При `meta.truncated=true` сообщи, что список неполный.
- `show <iid>` — MR по его номеру внутри проекта.
- `create` — создание MR из JSON через `--input`. Обязательны `source_branch`, `target_branch`, `title`; необязательны `description`, `remove_source_branch`, `squash`.
- `merge <iid>`, `approve <iid>` — запись с обязательным `--sha` проверенного HEAD MR (40 или 64 hex-символа).

Все записи требуют `--operation-id`. Разрешение создать MR само по себе не разрешает merge или approve. Для merge/approve возьми SHA из просмотренного MR и проверь относящиеся к нему изменения. При смене HEAD заново проверь изменения и границы разрешения; не подставляй новый SHA автоматически. SHA входит в запрос и отпечаток операции.

Перед первым вызовом прочитай [общий контракт CLI](../_shared/CONTRACT.md). Запуск: [scripts/mr.py](scripts/mr.py).

```text
python "<skill-dir>/scripts/mr.py" --project group/project --action show 17
python "<skill-dir>/scripts/mr.py" --project group/project --action create --input "<absolute-path>/mr.json" --operation-id <stable-id>
python "<skill-dir>/scripts/mr.py" --project group/project --action merge 17 --sha <reviewed-sha> --operation-id <stable-id>
```
