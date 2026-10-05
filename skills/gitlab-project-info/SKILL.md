---
name: gitlab-project-info
description: "Чтение настроек проекта GitLab: основные поля, merge settings, approval rules и настройки их переопределения, push rules и protected branches. Для оценки по чек-листу используй gitlab-repo-check."
---

Покажи настройки проекта. `--project` принимает путь `group/project`, числовой ID или псевдоним из профиля. CLI только читает настройки.

`push_rules=null` означает, что правила не настроены либо недоступны. `meta.unavailable` перечисляет недоступные ресурсы; `meta.truncated=true` обозначает неполные списки. Отсутствующее поле или недоступные данные не подтверждают отсутствие ограничения.

`approval_rules` содержит проектные правила согласований, `approval_settings` — запрет их переопределения в отдельных MR. `approval_settings=null` означает недоступность настройки.

Перед первым вызовом прочитай [общий контракт CLI](../_shared/CONTRACT.md). Запуск: [scripts/project_info.py](scripts/project_info.py).

```text
python "<skill-dir>/scripts/project_info.py" --project group/project
```
