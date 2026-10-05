# ai_agents_harness

Переносимый harness для AI-агентов (Kimi Code, Claude Code, Codex): скилы,
конфиги и скрипт установки. Один репозиторий — источник истины для всех
рабочих машин и всех агентских инструментов.

## Что внутри

```
ai_agents_harness/
├── README.md            ← этот файл
├── install.sh           ← раскатка на новую машину (Git Bash)
├── skills/              ← скилы, общие для всех инструментов
├── config/
│   └── kimi/            ← шаблоны конфигов Kimi Code
├── .env.example         ← переменные окружения (шаблон, без значений)
└── .gitignore
```

## Скилы

| Скил | Что делает |
|---|---|
| `bitrix-task` | Создать задачу в Bitrix24 из контекста разговора |
| `bitrix-get-task` | Показать задачу Bitrix24 по ID |
| `bitrix-list-tasks` | Список задач по роли (постановщик/исполнитель/...) |
| `bitrix-update-task` | Изменить поля задачи (описание, дедлайн, приоритет) |
| `bitrix-close-task` | Закрыть задачу |
| `bitrix-comment-task` | Добавить комментарий к задаче |
| `bitrix-get-chat-messages` | Прочитать последние сообщения чата |
| `bitrix-send-chat-message` | Отправить сообщение в чат |
| `fastapi-patterns` | Эталонная архитектура FastAPI-проектов (endpoint → service → repository → client) |
| `next-js` | Справочник Next.js App Router |
| `frontend-design` | Правила production-ready UI |
| `explain-code` | Понятное объяснение кода |
| `git-commit-push` | Безопасный коммит и push по шаблону |

Скилы написаны в переносимом формате: `SKILL.md` с frontmatter (`name`,
`description`), пути к скриптам — относительные от каталога скила. Это
понимают Kimi Code, Claude Code и Codex.

## Требования

- Python 3.10+ в PATH (скрипты bitrix-* используют только стандартную библиотеку)
- Git Bash (Windows) или обычный bash (Linux/macOS)
- Один или несколько агентских инструментов: Kimi Code, Claude Code, Codex

## Установка на новую машину

```bash
git clone https://github.com/BKSLab/ai_agents_harness.git
cd ai_agents_harness
bash install.sh
```

`install.sh`:

1. **Kimi Code** — добавляет в `~/.kimi-code/config.toml` параметр
   `extra_skill_dirs`, указывающий на каталог `skills/` этого репозитория.
   Скилы не копируются: `git pull` сразу обновляет сетап.
2. **Claude Code / Codex** — копирует скилы в `~/.claude/skills/` и
   `~/.codex/skills/`, если эти каталоги существуют. Для обновления скилов
   запусти `install.sh` повторно после `git pull`.
3. Проверяет наличие Python.

После установки перезапусти агента — скилы подхватываются при старте сессии.

## Секреты

Секреты в репозитории не хранятся. Скрипты `bitrix-*` читают webhook из
переменной окружения `BITRIX_WEBHOOK`:

```bash
# Windows (постоянно, для новых процессов):
setx BITRIX_WEBHOOK "https://<портал>/rest/<user_id>/<token>/"

# Linux/macOS (~/.bashrc):
export BITRIX_WEBHOOK="https://<портал>/rest/<user_id>/<token>/"
```

Формат значения — в `.env.example`. Где взять: Bitrix24 → Разработчикам →
Входящий вебхук.

## Проверка после установки

```bash
# 1. Скилы видны агенту: в новой сессии набери /skill: — автодополнение покажет список
# 2. Скрипты работают (read-only проверка):
python "<репозиторий>/skills/bitrix-list-tasks/scripts/list_tasks.py" creator active
# 3. Без BITRIX_WEBHOOK скрипт обязан упасть с понятной ошибкой, а не traceback'ом
```

## Как добавить новый скил

1. Создай `skills/<имя-скила>/SKILL.md` с frontmatter: `name` и `description`
   обязательны, без них скил не зарегистрируется.
2. В `description` пиши, когда скил вызывать — по нему агент решает,
   подключать скил автоматически.
3. Пути к скриптам — только относительные от каталога скила
   (`scripts/do_thing.py`), без абсолютных путей и платформенных плейсхолдеров.
4. Секреты — только через переменные окружения, значения не коммитить.
5. Коммит, push; на остальных машинах `git pull` (+ `install.sh` для
   Claude/Codex).

## Обновление сетапа

```bash
git pull          # Kimi Code: готово (extra_skill_dirs смотрит в репозиторий)
bash install.sh   # Claude Code / Codex: обновить копии
```
