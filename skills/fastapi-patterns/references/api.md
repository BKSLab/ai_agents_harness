# Эндпоинты и Pydantic-схемы

> Часть скилла `fastapi-patterns`. Читать при написании или правке любого
> эндпоинта и схемы запроса/ответа.

---

## Эндпоинты (`api/v1/endpoints/*.py`)

Каждый эндпоинт оформляется максимально полно для автогенерируемой документации:

```python
@router.post(
    path="/items",
    status_code=status.HTTP_201_CREATED,
    summary="Краткое описание для списка эндпоинтов",
    description="Подробное описание бизнес-смысла операции.",
    operation_id="createItem",
    response_description="Что именно возвращается в ответе",
    responses={
        201: {"description": "...", "content": {"application/json": {"example": {...}}}},
        404: {"description": "...", "content": {"application/json": {"example": {"detail": "..."}}}},
        500: {"description": "...", "content": {"application/json": {"example": {"detail": "..."}}}},
    },
    response_model=ResponseSchema,
)
async def endpoint_name(
    data: RequestSchema,
    service: ServiceDep,
) -> ResponseSchema:
    """Что делает эндпоинт.

    Args:
        data: ...
        service: ...

    Returns:
        ...
    """
    logger.info("🚀 Запрос POST /items. Параметр: %s.", data.field)
    try:
        result = await service.do_something(...)
        logger.info("✅ Запрос POST /items выполнен.")
        return result
    except (DomainErrorA, DomainErrorB, DomainErrorC) as error:
        logger.exception("❌ Ошибка при ... Параметр: %s. Детали: %s", data.field, error)
        raise HTTPException(status_code=error.status_code, detail=error.detail)
```

Обязательные элементы:
- `summary`, `description`, `response_description`, `operation_id` — заполняются всегда, даже для тривиальных эндпоинтов. `operation_id` в camelCase — он используется при генерации клиентских SDK.
- `responses` со всеми реалистичными кодами ошибок (401/403/404/422/500 — в зависимости от того, что реально может произойти), с примером тела ответа. Это не формальность — именно отсюда фронтенд и клиенты API узнают контракт ошибок без чтения кода.
- Параметры запроса — всегда `Annotated[Тип, Query(description=...)]` / `Path(description=...)`, никогда "голые" аргументы без описания.
- Docstring в Google-стиле (`Args`/`Returns`/`Raises`) — обязателен даже когда сигнатура самодокументирована, потому что докстринг описывает поведение, а не сигнатуру.
- `try/except` перехватывает **только перечисленные** доменные исключения нижних слоёв (никогда голый `except Exception`). Если исключение не предусмотрено — пусть всплывёт как 500 со стектрейсом, это сигнал, что в коде пропущен кейс.
- Эндпоинт объявляется как `async def`. `def`-эндпоинт целиком уезжает в ограниченный пул потоков Starlette — это осознанный выбор для синхронного по природе кода, а не умолчание (скилл `fastapi-services`).
- Конвертация доменного исключения в HTTP-ответ — всегда одинаковая идиома: `raise HTTPException(status_code=error.status_code, detail=error.detail)`, потому что у каждого доменного исключения есть `status_code` и `.detail` (см. `errors.md`).

### Логирование в эндпоинте

- Пара `logger.info` на каждый публичный эндпоинт: 🚀 на входе с ключевыми параметрами запроса, ✅ на выходе после успешного выполнения. Без первой записи не отличить «запрос не дошёл» от «запрос упал внутри», без второй — «ответ отдан» от «висим на внешнем вызове».
- Эндпоинт — единственное место, где вызывается `logger.exception(...)`: здесь ошибка окончательно обработана и превращается в HTTP-ответ, поэтому именно здесь нужен полный traceback. Слои ниже до этой точки логируют без него, иначе одна ошибка даёт три стектрейса в логе.
- В сообщение подставляются те параметры, по которым потом будут искать конкретный случай (идентификатор сущности, внешний id), а не всё тело запроса — и никогда содержимое полей с секретами.

## Pydantic-схемы

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ItemCreateRequest(BaseModel):
    """Тело запроса для создания новой записи Item."""

    model_config = ConfigDict(
        json_schema_extra={
            'example': {
                'external_id': 'ext-12345',
                'title': 'Пример названия',
            }
        }
    )

    external_id: str = Field(
        ...,
        description='Идентификатор сущности во внешней системе.',
        examples=['ext-12345'],
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description='Название сущности.',
        examples=['Пример названия'],
    )


class ItemSchema(BaseModel):
    """Схема Item для ответов API — строится напрямую из ORM-объекта."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description='Уникальный идентификатор записи.', examples=[1])
    external_id: str = Field(..., description='Идентификатор сущности во внешней системе.', examples=['ext-12345'])
    title: str = Field(..., description='Название сущности.', examples=['Пример названия'])
    description: str = Field(
        '',
        description='Описание сущности.',
        examples=['Краткое описание записи.'],
    )

    @field_validator('description', mode='before')
    @classmethod
    def none_to_empty_string(cls, v: object) -> str:
        return '' if v is None else v


class ItemsListSchema(BaseModel):
    """Пагинированный список записей Item."""

    total: int = Field(..., description='Общее количество записей, удовлетворяющих фильтрам.', examples=[42])
    page: int = Field(..., description='Текущий номер страницы.', examples=[1])
    page_size: int = Field(..., description='Количество записей на странице.', examples=[10])
    items: list[ItemSchema] = Field(..., description='Список записей на текущей странице.')
```

Ключевые моменты этого примера:
- **Каждое поле — `Field(..., description=..., examples=[...])`**, даже там, где имя поля кажется самоочевидным — описание уходит прямо в OpenAPI/Swagger UI, а `examples` — в автогенерируемые примеры запросов/ответов.
- `model_config = ConfigDict(json_schema_extra={'example': {...}})` на схеме **запроса** — даёт цельный пример тела запроса в Swagger, а не только поэлементные примеры по каждому полю.
- `ConfigDict(from_attributes=True)` на схеме **ответа** — позволяет `ItemSchema.model_validate(orm_object)` напрямую, без промежуточного `.__dict__`/ручной сборки словаря.
- `@field_validator(..., mode='before')` — нормализация "грязных" значений из ORM/внешнего источника (например, `NULL` в колонке, которая по контракту API всегда строка) в момент валидации, а не точечными проверками в сервисе перед каждым возвратом схемы.
- Схема списка едина для всех эндпоинтов, но способ выборки под ней — offset или keyset — выбирается по размеру и характеру данных (скилл `fastapi-data`).
- Схема пагинированного списка (`ItemsListSchema`) всегда содержит `total`/`page`/`page_size`/`items` — единообразно для всех списочных эндпоинтов проекта.

Остальные правила:
- `@field_validator(..., mode='before')`, применённый сразу к нескольким полям одного типа одной декорацией (`@field_validator('field_a', 'field_b', mode='before')`), а не дублированием одинаковой проверки на каждое поле по отдельности.
- Одна и та же сущность в разных контекстах (краткий список / детальный просмотр / сохранённая выборка) — по возможности **одна общая схема**, а не три почти одинаковые. Разные представления получаются через опциональность полей с пустыми default'ами, а не через дублирование классов.
- Исключение из правила "одна схема" — когда публичное имя поля в API должно отличаться от внутреннего имени колонки в БД (например, БД хранит `legacy_code`, а контракт API отдаёт его как `category_code`, потому что для внешнего клиента это и есть осмысленное имя). В этом случае оправданно завести **две** схемы: публичную с `Field(..., validation_alias='legacy_code')` (переименование при чтении из ORM-объекта) для эндпоинтов, и внутреннюю с настоящими именами полей для сервисов/репозиториев, где переименование было бы только лишней путаницей. Критерий разделения — расхождение в именовании или составе полей между "что отдаём наружу" и "что используем внутри", а не "контекст использования" сам по себе.

