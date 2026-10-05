# Changelog

Формат: [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/). Версия — в pyproject.toml.

## [0.3.0] — 2026-10-05

### Добавлено

- Скил `dev-pipeline`: полный цикл разработки задачи — от ознакомления через риски, план и реализацию до независимого ревью и фиксации. Два гейта пользователя: план и отправка кода.
- Скил `risk-assessment` с чек-листом рисков: контракты, потребители, данные, конкурентность, внешние системы, откат, наблюдаемость, безопасность.
- Скил `code-review` с чек-листом и строгим форматом вердикта (approved + findings с severity и location).
- Шаблон `templates/project-AGENTS.md` для проектов: команды, потребители и контракты, рисковые места.
- Глобальные правила `global/AGENTS.md` (устанавливаются в `~/.agents/AGENTS.md` или аналог инструмента).
- Хуки Kimi Code: `hooks/protect_secrets.py` (барьер на чтение секретов через shell) и `hooks/lint_on_edit.py` (ruff после правки .py), фрагмент конфигурации `config/kimi/hooks.toml`. Подключение ручное, по README.
- Eval-сценарии для трёх новых скилов (всего 18).

## [0.2.0] — 2026-10-05

### Добавлено

- Общий клиент Bitrix (`skills/_shared/`): единый runtime, JSON-контракт, журнал операций SQLite с operation-id.
- Установщик `harness_cli` с квитанциями, откатом и dry-run; `manage.py`: install, doctor, check, eval, operations, export-public.
- Тесты pytest и GitHub Actions на трёх ОС; evals решений модели.
- Раздельные переменные BITRIX_PORTAL_URL / BITRIX_WEBHOOK_USER_ID / BITRIX_WEBHOOK_TOKEN; BITRIX_WEBHOOK объявлен устаревшим.

### Изменено

- Скрипты bitrix-* стали тонкими обёртками над общим runtime.
- README переписан: установка, частная конфигурация, приватность истории.

## [0.1.0] — 2026-09-21

### Добавлено

- 13 скилов: восемь инструментов Bitrix24, fastapi-patterns, next-js, frontend-design, explain-code, git-commit-push.
- install.sh, шаблоны конфигов Kimi, первичная структура репозитория.
