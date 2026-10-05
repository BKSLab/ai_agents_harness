# Dependency Injection

> Часть скилла `fastapi-patterns`. Читать при добавлении новой зависимости,
> сервиса, репозитория, авторизации, WebSocket/SSE-маршрута.

---

Трёхуровневая система Depends-фабрик, зеркалящая слои архитектуры, плюс эндпоинт как потребитель верхнего уровня:

- **Уровень 0** — `dependencies/db_session.py`: низкоуровневая зависимость сессии БД (`AsyncGenerator` + `async with`).
- **Уровень 1** — `dependencies/repositories.py`: фабрики репозиториев, принимающие сессию через `Depends`.
- **Уровень 2** — `dependencies/services.py`: фабрики сервисов, принимающие репозитории/клиенты/другие сервисы через `Depends`.
- **Уровень 3** — эндпоинт: не фабрика, а потребитель — получает готовый объект сервиса одним параметром и ничего не знает об уровнях 0–2.

Каждая фабрика сопровождается готовым типом-алиасом `Annotated[Тип, Depends(фабрика)]` с суффиксом `Dep`, который и используется в сигнатурах эндпоинтов и других фабрик. Это убирает повторение `Depends(...)` по всему коду и даёт единую точку, где можно изменить способ создания объекта.

Полная цепочка для одной сущности, от сессии БД до эндпоинта — четыре файла:

```python
# dependencies/db_session.py — уровень 0: сессия БД
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as db_session:
        yield db_session

DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
```

```python
# dependencies/repositories.py — уровень 1: репозиторий поверх сессии
def get_items_repository(session: DbSessionDep) -> ItemsRepository:
    return ItemsRepository(session)

ItemsRepositoryDep = Annotated[
    ItemsRepository, Depends(get_items_repository)
]
```

```python
# dependencies/services.py — уровень 2: сервис поверх репозитория (и любых других зависимостей)
async def get_items_service(
    items_repository: ItemsRepositoryDep,
    other_service: OtherServiceDep,
) -> ItemsService:
    """Фабрика для создания экземпляра сервиса работы с сущностью Item."""
    return ItemsService(
        items_repository=items_repository,
        other_service=other_service,
    )

ItemsServiceDep = Annotated[ItemsService, Depends(get_items_service)]
```

```python
# api/v1/endpoints/items.py — уровень 3: эндпоинт получает готовый сервис одним параметром
@router.get(path="/{item_id}", response_model=ItemSchema)
async def get_item(item_id: str, service: ItemsServiceDep) -> ItemSchema:
    return await service.get_item(item_id=item_id)
```

Эндпоинт не видит ни `db_session`, ни `ItemsRepository` — FastAPI разворачивает граф зависимостей сам, а в сигнатуре остаётся только осмысленное имя `service`. Каждый уровень знает только о том, что стоит непосредственно под ним.

### Авторизация как Depends-зависимость

Проверка API-ключа реализуется как обычная Depends-зависимость (`VerifyApiKeyDep`), которая сама перехватывает доменные исключения и поднимает `HTTPException` — это единственное место, где Depends-слой сам бросает HTTP-исключение напрямую, потому что у него нет "вышестоящего" эндпоинта, который сделает это за него.

**Двухуровневая авторизация.** Если в проекте есть и обычные клиенты API, и привилегированные операции управления самим API (выпуск/отзыв ключей), это две независимые плоскости доступа с разными секретами:
- Обычный доступ — `X-API-Key` в заголовке, хешированный ключ в БД, проверяется через сервис и репозиторий (генерация и проверка ключа — `services.md`, подраздел «Секреты и API-ключи»).
- Управление ключами — отдельный `X-Master-Key`, сверяется напрямую с одним значением из `Settings` (`master_api_key.get_secret_value()`), без обращения к БД. Не подменять одно другим: мастер-ключ не должен попадать в таблицу ключей, а обычный API-ключ не должен давать доступ к управлению ключами.

### Жизненный цикл HTTP-клиента для внешних API

`httpx.AsyncClient`, который передаётся в клиентов внешних API (`services.md`) через `Depends`, может жить по одной из двух схем — выбор фиксируется один раз и одинаково для всех клиентов в проекте, не смешивается без причины:
- **shared/lifespan-managed** (схема по умолчанию) — один `httpx.AsyncClient` создаётся в `lifespan`, переиспользуется во всех запросах через `app.state` и закрывается при остановке приложения. Сохраняет keep-alive соединения и TLS-сессии между запросами и создаёт SSL-контекст один раз на процесс.
- **per-request** — `async def get_http_session(): async with httpx.AsyncClient(...) as client: yield client`, новый клиент на каждый запрос. Проще и не требует синхронизации жизненного цикла с `lifespan`, но платит за это: каждый запрос к внешнему API начинается с нового TCP-соединения и полного TLS-рукопожатия, а построение SSL-контекста читает CA-бандл с диска внутри event loop. Уместно для редких вызовов и там, где нужна изоляция состояния между запросами (разные учётные данные, разные базовые URL), но не как схема по умолчанию для горячего пути.

Независимо от схемы: клиент внешнего API не создаёт `httpx.AsyncClient` внутри своих методов «если не передали». Такая ветка молча отменяет выбранную схему и делает реальный жизненный цикл невидимым в месте вызова — отсутствие обязательной зависимости должно быть ошибкой сборки графа, а не тихим fallback.

### Долгоживущие соединения: WebSocket, SSE, streaming

Зависимость с `yield` освобождается не после выполнения полезной работы, а после выхода из обработчика. Для обычного HTTP-запроса это десятки миллисекунд, поэтому разница незаметна. Для WebSocket, Server-Sent Events и streaming-ответа обработчик живёт минуты и часы — и всё это время удерживает всё, что получил через `Depends`.

Отсюда правило: **долгоживущий обработчик не получает через `Depends` ничего, что удерживает ограниченный ресурс** — ни сессию БД, ни HTTP-клиент, ни объекты, построенные поверх них (репозитории, сервисы, авторизационные зависимости с обращением к БД).

Аутентификация и проверка доступа при этом никуда не деваются, они просто выполняются в собственном коротком scope до перехода в долгоживущую фазу:

```python
# WebSocket-маршруты живут в собственном роутере — см. про зависимости роутера ниже
ws_router = APIRouter()


@ws_router.websocket("/{item_id}/events/ws")
async def item_events_websocket(
    websocket: WebSocket,
    item_id: uuid.UUID,
    hub: RealtimeHubDep,  # объект из app.state, ограниченных ресурсов не держит
) -> None:
    """Подписывает пользователя на события сущности."""
    async with async_session_factory() as session:
        service = build_access_service(session)
        principal = await service.resolve_principal(websocket.headers)
        if principal is None:
            await websocket.close(code=4401)
            return
        if not await service.can_read_item(principal, item_id=item_id):
            await websocket.close(code=4403)
            return
    # сессия закрыта здесь — до входа в долгоживущую фазу

    await websocket.accept()
    await hub.connect(topic_for(item_id), websocket)
    try:
        while True:
            await websocket.receive_text()
    finally:
        await hub.disconnect(topic_for(item_id), websocket)
```

- В долгоживущую фазу передаются только неизменяемые данные: идентификатор пользователя, идентификатор сущности, topic, hub. Если обработка входящего сообщения требует БД — на это сообщение открывается отдельная короткая сессия и сразу закрывается.
- Для handshake не собирается полный граф доменного сервиса. Нужны проверка доступа и транспорт, а не два десятка репозиториев и LLM-клиент, который после проверки не используется.
- **Зависимости уровня роутера применяются и к WebSocket-маршрутам.** `include_router(router, dependencies=[Depends(get_current_user)])` навесит зависимость на каждый маршрут роутера, включая сокеты, и она не видна в сигнатуре обработчика. Убрать параметр из сигнатуры недостаточно — маршруты долгоживущих соединений выносятся в отдельный роутер без router-level `dependencies`, а нужные проверки выполняются внутри обработчика.

Как выглядит нарушение в проде: число соединений к БД равно числу открытых вкладок, а не числу активных запросов; в `pg_stat_activity` видны соединения в состоянии `idle in transaction` с возрастом, равным времени жизни пользовательской сессии, и с `wait_event = ClientRead` — SQL давно выполнен, сервер БД ждёт приложение. Обычные HTTP-запросы при этом начинают упираться в `pool_timeout` и отказывать пачками, причём одновременно в несвязанных частях API.

Проверяется это одним тестом: открыть долгоживущих соединений больше, чем `pool_size + max_overflow`, и убедиться, что обычные HTTP-запросы продолжают отвечать, а число соединений к БД не растёт вместе с числом сокетов.

