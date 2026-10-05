# Тестирование

> Часть скилла `fastapi-patterns`. Читать перед написанием любого теста
> и при настройке тестового окружения проекта.

---

Тесты — обязательная часть архитектуры, не опциональная надстройка.

### Стратегия — пирамида тестов привязана к слоям

Слоистая архитектура («Слоистая архитектура» в SKILL.md) ценна тестами ровно настолько, насколько ею пользуются: каждый слой принимает зависимости через конструктор (`di.md`), значит каждый слой можно протестировать в изоляции, подсунув ему дублёр зависимости вместо реальной. Если этим не пользоваться, часть ценности архитектуры теряется — слои разделены, а проверяются всё равно только вручную через браузер/Postman.

| Слой | Тип теста | Что подменяется | Через что бежит |
|---|---|---|---|
| Сервис | unit | репозитории, клиенты, другие сервисы | `unittest.mock.AsyncMock(spec=...)` |
| Репозиторий | integration | ничего — реальная БД | `testcontainers` Postgres + реальная `AsyncSession` |
| Парсер/утилита | unit | ничего — чистая функция | прямой вызов с фикстурным словарём |
| Клиент внешнего API | unit | сетевой транспорт | `httpx.MockTransport` |
| Эндпоинт | integration (API-level) | сервис целиком (через `app.dependency_overrides`) | `httpx.AsyncClient` + `ASGITransport` |
| Граф зависимостей | архитектурный | ничего — проверяется собранное приложение | обход `app.routes` и `route.dependant` |

Правило выбора: **репозиторий тестируется на реальной БД, а не на моках сессии.** Мокать `db_session.execute(...)` бессмысленно — такой тест проверяет, что мок вызван с нужными аргументами, а не что SQL-запрос на самом деле возвращает корректные данные (особенно с Postgres-специфичными вещами: `ilike`, `JSONB`, `ON DELETE CASCADE`, составные `UniqueConstraint` — на SQLite в памяти эти тесты будут лгать). `testcontainers` поднимает настоящий Postgres в Docker на время тестового прогона — это и есть единственный способ честно проверить репозиторий.

### Структура каталога

```
tests/
├── conftest.py                  # общие фикстуры: testcontainers, db_session, async_client
├── unit/
│   ├── services/                 # один файл = один сервис, зеркалит app/services/
│   └── utils/                     # парсеры, security.py и т.п.
├── integration/
│   └── repositories/              # один файл = один репозиторий, зеркалит app/repositories/
└── api/
    └── endpoints/                  # один файл = один роутер, зеркалит app/api/v1/endpoints/
```

Та же логика "один файл — одна сущность", что и в основном коде (`project-layout.md`): тест на `ItemsService` лежит в `tests/unit/services/test_items_service.py`, тест на `ItemsRepository` — в `tests/integration/repositories/test_items_repository.py`.

### Фикстуры БД (`testcontainers` + реальный Postgres)

```python
# tests/conftest.py
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from db.models.base import Base


@pytest_asyncio.fixture(scope="session")
def postgres_container():
    """Один контейнер Postgres на весь тестовый прогон — поднимать его на каждый тест слишком дорого."""
    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest_asyncio.fixture(scope="session")
async def engine(postgres_container):
    url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    """Сессия на отдельный тест с rollback после — тесты не видят данные друг друга."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()
```

- Контейнер — `scope="session"` (поднимается один раз на весь прогон, дорогая операция). Схема создаётся один раз через `Base.metadata.create_all` (для тестов alembic-миграции не прогоняются — это лишнее звено, схема и так строится из тех же моделей).
- Сессия — `scope="function"` (фикстура по умолчанию), с `rollback()` после каждого теста — изоляция между тестами без пересоздания контейнера.

### Unit-тест сервиса — зависимости подменены дублёрами

```python
# tests/unit/services/test_items_service.py
from unittest.mock import AsyncMock

import pytest

from exceptions.items import ItemNotFoundError
from repositories.items import ItemsRepository
from services.items import ItemsService


@pytest.mark.asyncio
async def test_get_item_raises_not_found_when_repository_returns_none():
    repository = AsyncMock(spec=ItemsRepository)
    repository.get_by_id.return_value = None
    service = ItemsService(items_repository=repository)

    with pytest.raises(ItemNotFoundError) as exc_info:
        await service.get_item(item_id="missing")

    assert exc_info.value.status_code == 404
```

- `AsyncMock(spec=ItemsRepository)` — `spec=` обязателен: без него мок тихо проглотит вызов несуществующего метода (например, после рефакторинга репозитория), и тест продолжит ложно зеленеть.
- Проверяется не просто факт исключения, а **конкретный тип и его `status_code`** — то, что реально долетит до клиента API через `raise HTTPException(status_code=error.status_code, ...)` в эндпоинте (`api.md`). Тест на "просто упало с ошибкой" не отличает 404 от 500.
- Сервис тестируется через его публичный интерфейс (`get_item`), не через приватные методы — приватные методы (`_normalize_*`, `_validate_*`) проверяются неявно, как часть сценария публичного метода, который их вызывает.

### Integration-тест репозитория — на реальной БД

```python
# tests/integration/repositories/test_items_repository.py
import pytest

from repositories.items import ItemsRepository


@pytest.mark.asyncio
async def test_save_and_get_by_external_id(db_session):
    repository = ItemsRepository(db_session)
    await repository.save_item({"external_id": "ext-1", "title": "Тестовая запись"})

    item = await repository.get_by_external_id(external_id="ext-1")

    assert item is not None
    assert item.title == "Тестовая запись"


@pytest.mark.asyncio
async def test_get_by_external_id_returns_none_when_not_found(db_session):
    repository = ItemsRepository(db_session)

    item = await repository.get_by_external_id(external_id="does-not-exist")

    assert item is None
```

Здесь не мокается ничего — проверяется реальный SQL-запрос на реальном движке Postgres. Это медленнее unit-тестов, но именно репозиторий — тот слой, где баг почти всегда в деталях конкретного диалекта БД (регистронезависимый поиск, типы колонок, поведение constraint'ов), а не в логике Python.

### Тест клиента внешнего API — подмена транспорта, не сети

```python
# tests/unit/clients/test_external_api_client.py
import httpx
import pytest

from clients.external_api_client import ExternalApiClient


@pytest.mark.asyncio
async def test_get_item_returns_not_found_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ExternalApiClient(httpx_client=httpx_client)

    result = await client.get_item(item_id="missing")

    assert result["search_status"] == "not_found"
```

`httpx.MockTransport` подменяет именно транспортный слой httpx, а не сам клиент — код клиента (`_request_to_api`, обработка `httpx.HTTPStatusError`) реально выполняется и проверяется, без обращения к сети.

### API-тест эндпоинта — через `dependency_overrides`

```python
# tests/api/endpoints/test_items.py
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from dependencies.services import get_items_service
from exceptions.items import ItemNotFoundError
from main import app
from services.items import ItemsService


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_item_endpoint_returns_404_with_detail():
    fake_service = AsyncMock(spec=ItemsService)
    fake_service.get_item.side_effect = ItemNotFoundError(item_id="missing")
    app.dependency_overrides[get_items_service] = lambda: fake_service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/items/missing")

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]
```

- `app.dependency_overrides[get_items_service] = ...` подменяет ровно ту фабрику, что зарегистрирована в `dependencies/services.py` (`di.md`) — благодаря тому, что в эндпоинте используется именно type alias `ItemsServiceDep`, а не ручной вызов сервиса, подмена работает без единой правки в коде эндпоинта.
- Этот уровень теста не проверяет бизнес-логику (она уже проверена unit-тестами сервиса) — он проверяет **контракт HTTP**: правильный код ответа, что `detail` долетел до тела ответа, что роутинг и сериализация `response_model` работают. Дублировать здесь все ветки бизнес-логики сервиса — не нужно.
- `clear_overrides` автоиспользуемая фикстура — без неё override, выставленный в одном тесте, протечёт в следующий и даст ложный результат.

### Архитектурный тест — готовый скелет

Правило без готового кода почти никогда не внедряют, поэтому тест границ слоёв заводится сразу, а не «когда-нибудь»:

```python
# tests/architecture/test_layers.py
import ast
import pathlib

import pytest

APP_ROOT = pathlib.Path(__file__).resolve().parents[2] / "app"

# Что какому слою запрещено импортировать
FORBIDDEN = {
    "api": ("repositories", "sqlalchemy", "db.session"),
    "services": ("fastapi", "sqlalchemy"),
    "repositories": ("fastapi",),
}


def _imported_modules(path: pathlib.Path) -> set[str]:
    """Собирает имена модулей, импортируемых в одном файле."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("layer, forbidden", FORBIDDEN.items())
def test_layer_does_not_import_forbidden_modules(layer: str, forbidden: tuple[str, ...]) -> None:
    violations = [
        f"{path.relative_to(APP_ROOT)} → {module}"
        for path in (APP_ROOT / layer).rglob("*.py")
        for module in _imported_modules(path)
        if module.startswith(forbidden)
    ]

    assert not violations, "Нарушение границ слоёв:\n" + "\n".join(violations)
```

- Набор запретов расширяется по мере появления правил: «сервис не импортирует `HTTPException`», «модель не импортирует схему», «эндпоинт не импортирует клиента внешнего API».
- Тест по импортам ловит статические нарушения. Ограничения, которые видны только в собранном приложении, — «долгоживущий маршрут не удерживает сессию БД», «у каждого роутера есть префикс версии» — проверяются вторым тестом, обходящим `app.routes` и `route.dependant`.

### Соглашения

- Имя теста — `test_<метод_или_сценарий>_<условие>_<ожидаемый_результат>` (например, `test_get_item_raises_not_found_when_repository_returns_none`) — по названию понятно, что именно проверяется, без чтения тела теста.
- Структура теста — Arrange / Act / Assert, разделённые пустой строкой, без явных комментариев-разделителей (структура должна быть видна по форме, не по подписям).
- Не тестируется то, что гарантирует сама библиотека (Pydantic корректно валидирует типы, SQLAlchemy корректно строит SQL для `select(...)`) — тестируется код проекта: ветвление, обработка ошибок, маппинг исключений, граничные случаи бизнес-правил (TTL истёк/не истёк, все источники недоступны одновременно, дубликат vs новая запись).
- Каждое новое доменное исключение (`errors.md`) — минимум один тест, что сервис/репозиторий действительно его поднимает в нужном сценарии, и (на уровне API-теста) что оно мапится в правильный `status_code`.
- Архитектурные ограничения проверяются тестом, а не договорённостью. Правила вида «эндпоинт не импортирует репозиторий», «сервис не знает о HTTP», «долгоживущий маршрут не удерживает сессию БД» проверяются либо разбором исходников через `ast`, либо обходом собранного графа зависимостей приложения. Такой тест ловит нарушение у всего кода сразу, включая тот, который напишут через год, и не зависит от того, вспомнил ли автор про правило на ревью. Правила, которые дёшево выразить тестом, но оставленные только в документации, нарушаются предсказуемо.

Отдельно стоит класс дефектов, который не ловится ни одним тестом на корректность: пороговые отказы. Утечка соединения из пула, неограниченный рост очереди, ресурс, удерживаемый дольше нужного — при малой нагрузке всё это работает идеально и ломается разом при превышении порога. Функциональные тесты, ревью и локальный запуск такое не показывают в принципе, потому что при одном-двух пользователях порог недостижим. Единственная защита — тест, который сознательно превышает предел: открыть соединений больше размера пула, поставить в очередь больше сообщений, чем обрабатывается за интервал, и проверить, что система деградирует предсказуемо, а не отказывает целиком.
- CI обязан гонять тесты **до** шага деплоя, а не параллельно или после — деплой не должен запускаться на сломанных тестах. Тестовый шаг в CI закладывается с первого коммита, а не добавляется постфактум, когда проект уже вырос.
