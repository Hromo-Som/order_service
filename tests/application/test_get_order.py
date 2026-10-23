from uuid import uuid4

import pytest

from src.application.usecases.create_order import CreateOrderUseCase, OrderDTO
from src.application.usecases.get_order import GetOrderUseCase
from src.domain.exceptions import OrderNotFoundError


async def test_get_order_returns_created(uow_factory, catalog):
    created = await CreateOrderUseCase(uow_factory, catalog)(
        OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1")
    )

    fetched = await GetOrderUseCase(uow_factory)(created.id)

    assert fetched.id == created.id
    assert fetched.status == created.status


async def test_get_order_not_found(uow_factory):
    with pytest.raises(OrderNotFoundError):
        await GetOrderUseCase(uow_factory)(uuid4())
