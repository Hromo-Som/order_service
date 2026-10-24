from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from src.application.ports.catalog import CatalogClient, CatalogItem
from src.application.ports.inbox import ProcessedEventsRepository
from src.application.ports.outbox import OutboxEvent, OutboxRepository
from src.application.ports.payments import PaymentDTO, PaymentsClient
from src.application.ports.repositories import OrderRepository
from src.domain.entities import Order
from src.domain.exceptions import ItemNotFoundError
from src.fastapi import create_app


class FakeEventPublisher:
    """In-memory EventPublisher: пишет в self.published, не в Kafka."""

    def __init__(self) -> None:
        self.published: list[dict] = []
        self.fail_next: bool = False

    async def publish(self, topic: str, key: str, payload: dict) -> None:
        if self.fail_next:
            self.fail_next = False
            raise httpx.ConnectError("Kafka unavailable")
        self.published.append({"topic": topic, "key": key, "payload": payload})


class InMemoryOutboxRepository(OutboxRepository):
    """In-memory замена SQLAlchemyOutboxRepository."""

    def __init__(self) -> None:
        self._storage: dict = {}

    async def add(
        self,
        topic: str,
        event_type: str,
        key: str,
        payload: dict,
        idempotency_key: str,
    ):
        event_id = uuid4()
        self._storage[event_id] = {
            "topic": topic,
            "event_type": event_type,
            "key": key,
            "payload": payload,
            "idempotency_key": idempotency_key,
            "published": False,
        }
        return event_id

    async def fetch_batch(self, limit: int) -> list[OutboxEvent]:
        result: list[OutboxEvent] = []
        for event_id, data in self._storage.items():
            if not data["published"]:
                result.append(
                    OutboxEvent(
                        id=event_id,
                        topic=data["topic"],
                        event_type=data["event_type"],
                        key=data["key"],
                        payload=data["payload"],
                        idempotency_key=data["idempotency_key"],
                        created_at=__import__("datetime").datetime.now(
                            __import__("datetime").UTC
                        ),
                    )
                )
            if len(result) >= limit:
                break
        return result

    async def mark_published(self, event_id) -> None:
        if event_id in self._storage:
            self._storage[event_id]["published"] = True

    def all(self) -> list[dict]:
        return list(self._storage.values())

    def unpublished(self) -> list[dict]:
        return [d for d in self._storage.values() if not d["published"]]


class InMemoryProcessedEventsRepository(ProcessedEventsRepository):
    """In-memory замена SQLAlchemyProcessedEventsRepository."""

    def __init__(self) -> None:
        self._processed: set[str] = set()

    async def try_mark_processed(self, dedup_key: str) -> bool:
        if dedup_key in self._processed:
            return False
        self._processed.add(dedup_key)
        return True

    def all(self) -> set[str]:
        return set(self._processed)


class FakePaymentsClient(PaymentsClient):
    """In-memory замена HttpPaymentsClient для use-case и API тестов."""

    def __init__(self, fail: bool = False) -> None:
        self._fail = fail
        self.calls: list[dict] = []
        self._payments: dict[str, PaymentDTO] = {}

    def set_fail(self, fail: bool) -> None:
        """Управлять поведением между вызовами в рамках одного теста."""
        self._fail = fail

    async def create_payment(
        self,
        order_id: str,
        amount: Decimal,
        callback_url: str,
        idempotency_key: str,
    ) -> PaymentDTO:
        self.calls.append(
            {
                "order_id": order_id,
                "amount": amount,
                "callback_url": callback_url,
                "idempotency_key": idempotency_key,
            }
        )
        if self._fail:
            raise httpx.ConnectError("Payments Service unavailable")
        dto = PaymentDTO(
            id=f"payment-{order_id}",
            order_id=order_id,
            amount=str(amount),
            status="pending",
            idempotency_key=idempotency_key,
        )
        self._payments[dto.id] = dto
        return dto


class InMemoryOrderRepository(OrderRepository):
    """Замена SQLAlchemy-репозитория для быстрых тестов."""

    def __init__(self) -> None:
        self._storage: dict[UUID, Order] = {}

    async def add(self, order: Order) -> Order:
        self._storage[order.id] = order
        return order

    async def get_by_id(self, order_id: UUID) -> Order | None:
        order = self._storage.get(order_id)
        return order.model_copy() if order else None

    async def get_by_idempotency_key(self, idempotency_key: str) -> Order | None:
        for order in self._storage.values():
            if order.idempotency_key == idempotency_key:
                return order
        return None

    async def update(self, order: Order) -> Order:
        if order.id not in self._storage:
            from src.domain.exceptions import OrderNotFoundError

            raise OrderNotFoundError(order.id)
        self._storage[order.id] = order
        return order

    async def get_by_id_for_update(self, order_id: UUID) -> Order | None:
        order = self._storage.get(order_id)
        return order.model_copy() if order else None

    def all(self) -> list[Order]:
        """Все сохранённые заказы — для assertion'ов в тестах."""
        return list(self._storage.values())


class InMemoryUoWContext:
    """Реализует UnitOfWorkContext (commit — маркер, add уже сохранил)."""

    def __init__(
        self,
        orders: InMemoryOrderRepository,
        outbox: InMemoryOutboxRepository,
        processed_events: InMemoryProcessedEventsRepository,
    ) -> None:
        self.orders = orders
        self.outbox = outbox
        self.processed_events = processed_events
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


class InMemoryUoWFactory:
    def __init__(
        self,
        orders: InMemoryOrderRepository | None = None,
        outbox: InMemoryOutboxRepository | None = None,
        processed_events: InMemoryProcessedEventsRepository | None = None,
    ) -> None:
        self._orders = orders or InMemoryOrderRepository()
        self._outbox = outbox or InMemoryOutboxRepository()
        self._processed_events = processed_events or InMemoryProcessedEventsRepository()

    @asynccontextmanager
    async def __call__(self) -> AsyncGenerator[InMemoryUoWContext]:
        yield InMemoryUoWContext(self._orders, self._outbox, self._processed_events)


class FakeCatalogClient(CatalogClient):
    """In-memory замена HttpCatalogClient."""

    def __init__(self, items: dict[str, CatalogItem] | None = None) -> None:
        self._items = items or {}
        self.calls: list[str] = []

    def set_item(self, item: CatalogItem) -> None:
        """Добавить товар после создания фикстуры — для специфичных тестов."""
        self._items[item.id] = item

    async def get_item(self, item_id: str) -> CatalogItem:
        self.calls.append(item_id)
        if item_id not in self._items:
            raise ItemNotFoundError(item_id)
        return self._items[item_id]


@pytest.fixture
def order_repo() -> InMemoryOrderRepository:
    return InMemoryOrderRepository()


@pytest.fixture
def uow_factory(
    order_repo: InMemoryOrderRepository,
    outbox: InMemoryOutboxRepository,
    processed_events: InMemoryProcessedEventsRepository,
) -> InMemoryUoWFactory:
    return InMemoryUoWFactory(order_repo, outbox, processed_events)


@pytest.fixture
def catalog() -> FakeCatalogClient:
    """Каталог с одним товаром: item-1, price=100.00, available_qty=10."""
    client = FakeCatalogClient()
    client.set_item(
        CatalogItem(id="item-1", name="Widget", price="100.00", available_qty=10)
    )
    return client


@pytest.fixture
def payments() -> FakePaymentsClient:
    return FakePaymentsClient()


@pytest.fixture
async def api_client(
    uow_factory: InMemoryUoWFactory,
    catalog: FakeCatalogClient,
    payments: FakePaymentsClient,
) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент к FastAPI без реального сервера и БД."""
    app = create_app()
    app.state.uow_factory = uow_factory
    app.state.catalog_client = catalog
    app.state.payments_client = payments
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def outbox() -> InMemoryOutboxRepository:
    return InMemoryOutboxRepository()


@pytest.fixture
def processed_events() -> InMemoryProcessedEventsRepository:
    return InMemoryProcessedEventsRepository()


@pytest.fixture
def publisher() -> FakeEventPublisher:
    return FakeEventPublisher()
