from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from src.application.ports.catalog import CatalogClient, CatalogItem
from src.application.ports.payments import PaymentDTO, PaymentsClient
from src.application.ports.repositories import OrderRepository
from src.domain.entities import Order
from src.domain.exceptions import ItemNotFoundError
from src.fastapi import create_app


class FakePaymentsClient(PaymentsClient):
    def __init__(self, fail: bool = False) -> None:
        self._fail = fail
        self.calls: list[dict] = []
        self._payments: dict[str, PaymentDTO] = {}

    def set_fail(self, fail: bool) -> None:
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
        return self._storage.get(order_id)

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
        return self._storage.get(order_id)

    def all(self) -> list[Order]:
        return list(self._storage.values())


class InMemoryUoWContext:
    """Реализует UnitOfWorkContext (commit — маркер, add уже сохранил)."""

    def __init__(self, orders: InMemoryOrderRepository) -> None:
        self.orders = orders
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


class InMemoryUoWFactory:
    """Реализует UnitOfWorkFactory через @asynccontextmanager __call__."""

    def __init__(self, orders: InMemoryOrderRepository | None = None) -> None:
        self._orders = orders or InMemoryOrderRepository()

    @asynccontextmanager
    async def __call__(self) -> AsyncGenerator[InMemoryUoWContext]:
        yield InMemoryUoWContext(self._orders)


class FakeCatalogClient(CatalogClient):
    def __init__(self, items: dict[str, CatalogItem] | None = None) -> None:
        self._items = items or {}
        self.calls: list[str] = []

    def set_item(self, item: CatalogItem) -> None:
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
def uow_factory(order_repo: InMemoryOrderRepository) -> InMemoryUoWFactory:
    return InMemoryUoWFactory(order_repo)


@pytest.fixture
def catalog() -> FakeCatalogClient:
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

    app = create_app()
    app.state.uow_factory = uow_factory
    app.state.catalog_client = catalog
    app.state.payments_client = payments
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
