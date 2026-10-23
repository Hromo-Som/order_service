import pytest

from src.application.usecases.create_order import CreateOrderUseCase, OrderDTO
from src.domain.enums import OrderStatusEnum
from src.domain.exceptions import InsufficientStockError, ItemNotFoundError


async def test_create_order_success(uow_factory, catalog, order_repo):
    usecase = CreateOrderUseCase(uow_factory, catalog)
    order = await usecase(
        OrderDTO(user_id="u1", item_id="item-1", quantity=2, idempotency_key="k1")
    )

    assert order.status == OrderStatusEnum.NEW
    assert order.quantity == 2
    assert order.idempotency_key == "k1"
    assert len(order_repo.all()) == 1


async def test_create_order_is_idempotent_by_key(uow_factory, catalog, order_repo):
    usecase = CreateOrderUseCase(uow_factory, catalog)
    dto = OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1")

    first = await usecase(dto)
    second = await usecase(dto)

    assert first.id == second.id
    assert len(order_repo.all()) == 1
    assert catalog.calls == ["item-1"]


async def test_create_order_different_keys_create_different_orders(
    uow_factory, catalog, order_repo
):
    usecase = CreateOrderUseCase(uow_factory, catalog)
    o1 = await usecase(OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1"))
    o2 = await usecase(OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k2"))

    assert o1.id != o2.id
    assert len(order_repo.all()) == 2


async def test_create_order_insufficient_stock(uow_factory, catalog):
    usecase = CreateOrderUseCase(uow_factory, catalog)
    with pytest.raises(InsufficientStockError) as exc:
        await usecase(OrderDTO(user_id="u1", item_id="item-1", quantity=999, idempotency_key="k1"))

    assert exc.value.item_id == "item-1"
    assert exc.value.requested == 999
    assert exc.value.available == 10


async def test_create_order_item_not_found(uow_factory, catalog):
    usecase = CreateOrderUseCase(uow_factory, catalog)
    with pytest.raises(ItemNotFoundError):
        await usecase(OrderDTO(user_id="u1", item_id="missing", quantity=1, idempotency_key="k1"))


async def test_create_order_does_not_persist_on_stock_error(uow_factory, catalog, order_repo):
    usecase = CreateOrderUseCase(uow_factory, catalog)
    with pytest.raises(InsufficientStockError):
        await usecase(OrderDTO(user_id="u1", item_id="item-1", quantity=999, idempotency_key="k1"))
    assert order_repo.all() == []
