# Order Service

Микросервис управления заказами на FastAPI с интеграцией Catalog, Payments,
Shipping и Notifications сервисов Capashino через HTTP и Kafka.

Реализован по принципам чистой архитектуры: `domain` не зависит ни от чего,
`application` — только от портов, `infrastructure` реализует порты, `presentation` —
адаптер HTTP. Kafka — через паттерны **Outbox** (надёжная публикация) и **Inbox**
(идемпотентная обработка).

---

## Оглавление

- [Возможности](#возможности)
- [Технологии](#технологии)
- [Структура проекта](#Структура-проекта)
- [API](#api)
- [События](#события)
- [Переменные окружения](#переменные-окружения)
- [Тесты](#тесты)
- [Миграции](#миграции)
- [Docker](#docker)
- [Деплой в Kubernetes](#деплой-в-kubernetes)

---

## Возможности

### Создание заказа и интеграция с Catalog
- `POST /api/orders` — создание заказа с проверкой наличия товара в Catalog.
- `GET /api/orders/{order_id}` — получение заказа.
- Идемпотентность через `idempotency_key`: повторный POST возвращает тот же заказ.
- Обработка ошибок Catalog: `ItemNotFoundError` → 400, `InsufficientStockError` → 400.

### Payments
- При создании заказа вызывается Payments Service и передаётся `callback_url`
  (внутренний Kubernetes DNS, не внешний домен).
- `POST /api/orders/payment-callback` — обработка асинхронного callback'а от Payments.
- Переходы: `NEW → PAID` при `succeeded`, `NEW → CANCELLED` при `failed`.
- Идемпотентность callback'ов через `SELECT ... FOR UPDATE` — параллельные
  callback'и на один заказ сериализуются.
- При ошибке создания платежа заказ переводится в `CANCELLED` в отдельной транзакции.

### Shipping через Kafka
- **Outbox**: `order.paid` пишется в `outbox_events` в той же транзакции,
  что и `NEW → PAID`. Отдельный relay публикует в Kafka.
- **Inbox**: `order.shipped` / `order.cancelled` дедуплицируются через
  `processed_events` (`INSERT ... ON CONFLICT DO NOTHING`).
- Consumer `student_system-shipment.events` обновляет статус заказа.
- Multi-replica safe: `SELECT ... FOR UPDATE SKIP LOCKED` в relay.

### Notifications
- Уведомления при каждом переходе статуса: `NEW`, `PAID`, `SHIPPED`, `CANCELLED`.
- Детерминированный `idempotency_key` = `order:<order_id>:<status>` — защита
  от дублей.
- Отправка **вне транзакции БД** — сбой Notifications не ломает заказ.
- 3 попытки с backoff на transient-ошибки Capashino.

---

## Технологии

- **Python 3.14+** (тестировано на 3.14)
- **FastAPI** + **Uvicorn** — HTTP API
- **SQLAlchemy 2.0** (async) + **asyncpg** — PostgreSQL
- **Alembic** — миграции БД
- **aiokafka** — Kafka producer / consumer
- **httpx** — HTTP-клиенты Capashino
- **Pydantic v2** + **pydantic-settings** — модели и конфигурация
- **uv** — управление зависимостями
- **pytest** + **pytest-asyncio** — тесты
- **ruff**  — линтер

---

## Структура проекта

```
order_service/
│
├── src/                                    # Код приложения
│   │
│   ├── domain/                             # ЯДРО — не зависит ни от чего
│   │   ├── __init__.py
│   │   ├── entities.py                     # Order (entity, @dataclass-like)
│   │   ├── enums.py                        # OrderStatusEnum
│   │   ├── events.py                       # OrderPaidEvent, ShipmentEvent, топики
│   │   └── exceptions.py                   # DomainError + наследники
│   │
│   ├── application/                        # Сценарии использования
│   │   ├── __init__.py
│   │   │
│   │   ├── ports/                          # Абстракции (ABC / Protocol)
│   │   │   ├── __init__.py
│   │   │   ├── catalog.py                  # CatalogClient, CatalogItem
│   │   │   ├── errors.py                   # UpstreamServiceError
│   │   │   ├── payments.py                 # PaymentsClient, PaymentDTO
│   │   │   ├── notifications.py            # NotificationsClient, NotificationDTO
│   │   │   ├── outbox.py                   # OutboxRepository, EventPublisher
│   │   │   ├── inbox.py                    # ProcessedEventsRepository
│   │   │   ├── repositories.py             # OrderRepository
│   │   │   └── uow.py                      # UnitOfWorkContext, UnitOfWorkFactory
│   │   │
│   │   ├── services/                       # Логика для нескольких use cases
│   │   │   ├── __init__.py
│   │   │   ├── notification_key.py         # build_idempotency_key
│   │   │   └── notification_service.py     # NotificationService (notify_*)
│   │   │
│   │   └── usecases/                       # Один файл — один сценарий
│   │       ├── __init__.py
│   │       ├── create_order.py             # POST /api/orders
│   │       ├── get_order.py                # GET /api/orders/{id}
│   │       ├── handle_payment_callback.py  # POST /payment-callback
│   │       └── handle_shipment_event.py    # Kafka consumer handler
│   │
│   ├── infrastructure/                     # Адаптеры — реализации портов
│   │   ├── __init__.py
│   │   │
│   │   ├── http/                           # HTTP-клиенты Capashino
│   │   │   ├── __init__.py
│   │   │   ├── catalog.py                  # HttpCatalogClient
│   │   │   ├── payments.py                 # HttpPaymentsClient
│   │   │   └── notifications.py            # HttpNotificationsClient
│   │   │
│   │   ├── messaging/                      # Kafka
│   │   │   ├── __init__.py
│   │   │   ├── kafka_producer.py           # KafkaEventPublisher
│   │   │   ├── kafka_consumer.py           # KafkaShipmentConsumer
│   │   │   ├── outbox_relay.py             # OutboxRelay (фоновый)
│   │   │   └── schemas.py                  # ShipmentEventPayload (Pydantic)
│   │   │
│   │   └── persistence/                    # PostgreSQL
│   │       ├── __init__.py
│   │       ├── database.py                 # create_engine, create_session_factory
│   │       ├── models.py                   # OrderORM, OutboxEventORM, ProcessedEventORM
│   │       ├── migrations.py               # run_migrations
│   │       ├── repositories.py             # SQLAlchemy реализация портов
│   │       └── uow.py                      # UnitOfWork
│   │
│   ├── presentation/                       # HTTP API
│   │   ├── __init__.py
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── dependencies.py             # DI-провайдеры, Annotated Dep
│   │       ├── schemas.py                  # Pydantic request/response
│   │       └── routes/
│   │           ├── __init__.py
│   │           └── orders.py               # POST, GET, /payment-callback
│   │
│   ├── __init__.py
│   ├── fastapi.py                          # create_app() — composition root API
│   ├── worker.py                           # run_worker() — composition root worker
│   └── settings.py                         # Settings (pydantic-settings)
│
├── tests/                                  # Тесты (повторяют src/)
│
├── alembic/                                # Миграции БД
│
├── bin/                                    # Точки входа
│   ├── api.py                              # uvicorn launcher
│   └── worker.py           # worker entrypoint (relay + consumer)
│
├── .dockerignore
├── .env.example                            # шаблон переменных (без секретов)
├── .gitignore
├── alembic.ini                             # конфиг Alembic
├── Dockerfile
├── pyproject.toml                          # зависимости, ruff/mypy/pytest
├── uv.lock                                 # lock-файл
└── README.md
```


**Правила зависимостей:**
- `domain` не импортирует ничего из `application`, `infrastructure`, `presentation`.
- `application` зависит только от `domain` и своих портов.
- `infrastructure` и `presentation` — адаптеры, собираются в composition root (`src/fastapi.py`).

**Диаграмма статусов:**

```
NEW ──pay──→ PAID ──ship──→ SHIPPED
│
└──cancel─────┴──cancel──→ CANCELLED
```
`SHIPPED` и `CANCELLED` — терминальные.

---

## API

### Создать заказ

```http
POST /api/orders
Content-Type: application/json

{
  "user_id": "user_1",
  "quantity": 1,
  "item_id": "550e8400-e29b-41d4-a716-446655440000",
  "idempotency_key": "unique-key-1"
}
```

**Ответ 201:** 

```
{
  "id": "c8501322-290d-457e-b473-b7ebdc8...",
  "user_id": "user_1",
  "item_id": "550e8400-e29b-41d4-a716-446655440000",
  "quantity": 1,
  "status": "NEW",
  "created_at": "2026-10-25T09:41:42.015422Z",
  "updated_at": "2026-10-25T09:41:42.015422Z"
}
```

### Коды ошибок

| Код | Причина |
|:---:|---|
| `400` | Товар не найден / недостаточно остатка |
| `422` | Невалидный payload (пустые поля, `quantity <= 0`) |
| `502` | Payments Service недоступен |

### Получить заказ

```http
GET /api/orders/{order_id}
```

**Ответы:**

- `200` — тот же JSON, что и при создании заказа.
- `404` — заказ не найден.
- `422` — невалидный UUID в пути.

### Callback от Payments

Внутренний эндпоинт, вызывается Payments Service асинхронно после обработки платежа.

```http
POST /api/orders/payment-callback
Content-Type: application/json
```

**Request body:**

```json
{
  "payment_id": "payment-uuid",
  "order_id": "order-uuid",
  "status": "succeeded",
  "amount": "200.00",
  "error_message": null
}
```

**Response:** всегда `200 OK`, чтобы Payments не ретраил заведомо бесполезные запросы. Если заказ не найден или статус терминальный — просто логируется, ответ всё равно `200`.

### Healthcheck

```http
GET /healthz
```

**Response `200 OK`:**

```json
{"status":"ok"}
```

---

## События

### Публикация: `order.paid` → `student_system-order.events`

```json
{
  "event_type": "order.paid",
  "order_id": "550e8400-e29b-41d4-a716-446655440000",
  "item_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "quantity": 1,
  "idempotency_key": "e8c9d4b2-..."
}
```

Публикуется через **Outbox**: запись в `outbox_events` в одной транзакции с
`NEW → PAID`, отдельный relay публикует в Kafka.

### Подписка: `student_system-shipment.events`

**`order.shipped`:**

```json
{
  "event_type": "order.shipped",
  "order_id": "...",
  "item_id": "...",
  "quantity": 1,
  "shipment_id": "ship-uuid"
}
```

**`order.cancelled`:**

```json
{
  "event_type": "order.cancelled",
  "order_id": "...",
  "item_id": "...",
  "quantity": 1,
  "reason": "Insufficient stock"
}
```

Обрабатывается **Inbox**-дедупликацией: `dedup_key = "{event_type}:{order_id}"`
записывается в `processed_events` атомарно с обновлением статуса.

---

## Переменные окружения

| Переменная | Обязательна | Описание | Пример |
|---|:---:|---|---|
| `DATABASE_URL` | ✅ | URL PostgreSQL (SQLAlchemy) | `postgresql+asyncpg://user:pass@host:5432/db` |
| `POSTGRES_CONNECTION_STRING` | ❌ | Сырая строка от платформы; конвертируется в `DATABASE_URL` | `postgres://user:pass@host/db` |
| `CAPASHINO_BASE_URL` | ✅ | Базовый URL Capashino API | `http://student-system-capashino-web.student-system-capashino.svc:8000` |
| `CAPASHINO_API_TOKEN` | ✅ | API-токен из профиля LMS | `abc123...` |
| `PAYMENT_CALLBACK_URL` | ✅ | URL нашего эндпоинта для callback'ов Payments. **Внутренний** Kubernetes DNS | `http://order-service.ns.svc:8000/api/orders/payment-callback` |
| `KAFKA_BOOTSTRAP_SERVERS` | ✅ | Адрес Kafka | `kafka.kafka.svc.cluster.local:9092` |
| `KAFKA_CONSUMER_GROUP` | ✅ | **Уникальное** имя группы consumer'а | `order-service-student-hromo-som-v3` |
| `KAFKA_AUTO_OFFSET_RESET` | ❌ | `latest` (по умолчанию) или `earliest` | `latest` |
| `OUTBOX_POLL_INTERVAL_SECONDS` | ❌ | Интервал relay'а | `1.0` |
| `OUTBOX_BATCH_SIZE` | ❌ | Размер пачки за один tick | `10` |
| `LOG_LEVEL` | ❌ | Уровень логирования | `INFO` |

### Важно про `PAYMENT_CALLBACK_URL`

Должен указывать на **внутренний** адрес Kubernetes:
`<service>.<namespace>.svc:<port>`, а не внешний `*.python-labs.ru` — иначе
Payments не сможет достучаться из кластера. Валидатор в `Settings` отсекает
внешний домен на старте приложения.

Узнать имя Service:

```bash
kubectl get svc -n <namespace>
```

---

## Тесты

```bash
# Все
uv run pytest -q

# С подробностями
uv run pytest -v --tb=short

# Только быстрые (domain + application)
uv run pytest tests/domain tests/application -q

# С покрытием
uv run pytest --cov=src --cov-report=term-missing
```

### Уровни тестов

| Каталог | Что покрывает |
|---|---|
| `tests/domain` | Сущность `Order`, переходы статусов |
| `tests/application` | Use cases (in-memory UoW, Fake клиенты) |
| `tests/application/services` | `NotificationService` |
| `tests/infrastructure` | HTTP-адаптеры через `MockTransport` |
| `tests/api` | FastAPI через `ASGITransport` (без сервера) |

### Линтер

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/
```

---

## Миграции

Схема БД управляется через **Alembic**. `create_all` **не используется** —
только миграции, применяемые автоматически при старте приложения
(`alembic upgrade head` в `lifespan`).

### Применить миграции вручную

```bash
DATABASE_URL=... uv run alembic upgrade head
```

### Сгенерировать миграцию после изменения моделей

```bash
# Нужна БД, совпадающая с текущим состоянием
# (иначе autogenerate «увидит» лишние diff'ы)
DATABASE_URL=... uv run alembic revision --autogenerate -m "add column X"

# Проверить глазами: alembic/versions/<hash>_add_column_x.py
# Убедиться, что нет неожиданных DROP

# Применить локально
DATABASE_URL=... uv run alembic upgrade head
```

### Откатить

```bash
DATABASE_URL=... uv run alembic downgrade -1
```

### Особенности

- **Initial migration идемпотентна**: `has_table("orders")` guard — безопасна
  для БД, созданной старым `create_all`.
- **`DROP TYPE IF EXISTS order_status` в `downgrade`** — PostgreSQL ENUM'ы
  независимы от таблиц, autogenerate не удаляет их сам.

---

## Docker

### Сборка

```bash
docker build -t order-service:local .
```

### Запуск

```bash
docker run --rm -p 8000:8000 \
  -e DATABASE_URL="postgresql+asyncpg://postgres:postgres@host.docker.internal:5432/orders" \
  -e CAPASHINO_BASE_URL="https://capashino.dev-2.python-labs.ru" \
  -e CAPASHINO_API_TOKEN="<токен>" \
  -e PAYMENT_CALLBACK_URL="http://order-service.ns.svc:8000/api/orders/payment-callback" \
  -e KAFKA_BOOTSTRAP_SERVERS="kafka.kafka.svc.cluster.local:9092" \
  -e KAFKA_CONSUMER_GROUP="order-service" \
  order-service:local
```

### Особенности образа

- **Multi-stage**: `uv` устанавливает зависимости в builder, runtime — только
  `.venv` + код.
- **Non-root** (`appuser:1000`).
- **`alembic.ini` и `alembic/`** копируются в образ — нужны для
  `_run_migrations`.

---

## Деплой в Kubernetes

Приложение деплоится через CI (GitHub Actions): тесты → сборка образа → пуш
в GHCR → вызов LMS API для деплоя.

### Переменные окружения в LMS Portal

Обязательно задать **все** из раздела
[Переменные окружения](#переменные-окружения). Особенно внимательно:

- **`PAYMENT_CALLBACK_URL`** — внутренний `<service>.<namespace>.svc:8000`,
  не внешний домен.
- **`KAFKA_CONSUMER_GROUP`** — **уникальный** (например,
  `order-service-<ваш-namespace>`), иначе события будут уходить другим
  студентам (общий consumer group).
- **`CAPASHINO_BASE_URL`** — внутренний URL Capashino:
  `http://student-system-capashino-web.student-system-capashino.svc:8000`.

### Проверка после деплоя

```bash
NS=<ваш-namespace>
POD=$(kubectl get pods -n "$NS" -o name | grep order-service | head -1 | cut -d/ -f2)

# Startup-логи
kubectl logs "$POD" -n "$NS" | head -30
# Ожидаемо:
#   Running alembic upgrade head...
#   Alembic migrations applied
#   Kafka producer запущен
#   Outbox relay запущен
#   Kafka consumer запущен
#   Application startup complete.

# alembic_version в БД
kubectl exec "$POD" -n "$NS" -- python -c "
import asyncio, os, asyncpg
async def main():
    url = os.environ['POSTGRES_CONNECTION_STRING'].replace('postgresql+asyncpg://', 'postgresql://')
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    conn = await asyncpg.connect(url)
    rows = await conn.fetch('SELECT version_num FROM alembic_version')
    print([r['version_num'] for r in rows])
    await conn.close()
asyncio.run(main())
"
# Ожидаемо: ['4ac6a0dff8f6']
```

### Диагностика

| Симптом | Что смотреть |
|---|---|
| `503` от nginx | `kubectl get pods` — Ready? `kubectl logs` — стартап? |
| `CrashLoopBackOff` | `kubectl logs <pod> --previous` — traceback |
| `No script_location key` | `alembic.ini` не в образе (Dockerfile) |
| `payment failed` в Capashino | `PAYMENT_CALLBACK_URL` — внутренний? |
| 1 из 3 notifications | `KAFKA_CONSUMER_GROUP` уникальный? `Retry` в логах? |
| `order.shipped` не приходит | Consumer group уникальный? Топик `student_system-shipment.events`? |

---

### Процессы

Сервис состоит из **двух** процессов, собираемых из одного образа:

| Процесс | Команда | Назначение |
|---|---|---|
| **API** | `uvicorn src.fastapi:create_app --factory` | HTTP API: создание/получение заказов, payment callback |
| **Worker** | `python bin/worker.py` | Outbox relay (публикация `order.paid` в Kafka) + Kafka consumer (`order.shipped`/`order.cancelled`) |

Оба используют те же порты/адаптеры (`UnitOfWork`, `KafkaEventPublisher`, ...),
но composition roots разные:
- `src/fastapi.py::create_app()` — API
- `src/worker.py::run_worker()` — worker

**Почему отдельный процесс**:
- API и relay/consumer масштабируются независимо
- Падение worker'а (OOM, Kafka-issue) не валит HTTP
- Мультиреплика: N API-подов + M worker-подов, `SKIP LOCKED` разводит relay,
  consumer group разводит партиции

---

## Лицензия

Учебный проект, не для продакшена.