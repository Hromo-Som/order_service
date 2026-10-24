from decimal import Decimal

import pytest

from src.application.usecases.create_order import CreateOrderUseCase, OrderDTO
from src.domain.enums import OrderStatusEnum
from src.domain.exceptions import (
    InsufficientStockError,
    ItemNotFoundError,
    PaymentCreationFailedError,
)

CALLBACK_URL = "http://order-service.ns.svc:8000/api/orders/payment-callback"


async def test_create_order_success(uow_factory, catalog, payments, order_repo):
    """Успешное создание заказа."""
    usecase = CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        payment_callback_url=CALLBACK_URL,
    )
    order = await usecase(
        OrderDTO(user_id="u1", item_id="item-1", quantity=2, idempotency_key="k1")
    )

    assert order.status == OrderStatusEnum.NEW
    assert order.quantity == 2
    assert order.idempotency_key == "k1"
    assert len(order_repo.all()) == 1


async def test_create_order_is_idempotent_by_key(
    uow_factory, catalog, payments, order_repo
):
    """Повторный вызов с тем же ключом не создаёт второй заказ и не ходит в Catalog."""
    usecase = CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        payment_callback_url=CALLBACK_URL,
    )
    dto = OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1")

    first = await usecase(dto)
    second = await usecase(dto)

    assert first.id == second.id
    assert len(order_repo.all()) == 1
    assert catalog.calls == ["item-1"]


async def test_create_order_different_keys_create_different_orders(
    uow_factory, catalog, payments, order_repo
):
    """Создание заказа с другим ключом создает другой заказ."""
    usecase = CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        payment_callback_url=CALLBACK_URL,
    )
    o1 = await usecase(
        OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1")
    )
    o2 = await usecase(
        OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k2")
    )

    assert o1.id != o2.id
    assert len(order_repo.all()) == 2


async def test_create_order_insufficient_stock(uow_factory, catalog, payments):
    """При недостаточном количестве товара выбрасывается ошибка InsufficientStockError."""
    usecase = CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        payment_callback_url=CALLBACK_URL,
    )
    with pytest.raises(InsufficientStockError) as exc:
        await usecase(
            OrderDTO(user_id="u1", item_id="item-1", quantity=999, idempotency_key="k1")
        )

    assert exc.value.item_id == "item-1"
    assert exc.value.requested == 999
    assert exc.value.available == 10


async def test_create_order_item_not_found(uow_factory, catalog, payments):
    """Поиск несуществующего товара выбрасывает ошибку ItemNotFoundError."""
    usecase = CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        payment_callback_url=CALLBACK_URL,
    )
    with pytest.raises(ItemNotFoundError):
        await usecase(
            OrderDTO(user_id="u1", item_id="missing", quantity=1, idempotency_key="k1")
        )


async def test_create_order_does_not_persist_on_stock_error(
    uow_factory, catalog, payments, order_repo
):
    """Недостаток стока — заказ не сохраняется вообще (нет NEW в БД)."""
    usecase = CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        payment_callback_url=CALLBACK_URL,
    )
    with pytest.raises(InsufficientStockError):
        await usecase(
            OrderDTO(user_id="u1", item_id="item-1", quantity=999, idempotency_key="k1")
        )
    assert order_repo.all() == []


async def test_create_order_calls_payments(uow_factory, catalog, payments, order_repo):
    """Проверяет контракт вызова Payments."""
    usecase = CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        payment_callback_url=CALLBACK_URL,
    )
    await usecase(
        OrderDTO(user_id="u1", item_id="item-1", quantity=2, idempotency_key="k1")
    )

    assert len(payments.calls) == 1
    call = payments.calls[0]
    assert call["amount"] == Decimal("200.00")
    assert call["callback_url"].startswith("http://order-service")
    assert call["idempotency_key"].endswith(":payment")


async def test_create_order_cancels_on_payment_failure(
    uow_factory, catalog, payments, order_repo
):
    """Ошибка Payments → заказ уже сохранён (NEW), затем переведён в CANCELLED."""
    payments.set_fail(True)
    usecase = CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        payment_callback_url="http://x",
    )

    with pytest.raises(PaymentCreationFailedError):
        await usecase(
            OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1")
        )

    orders = order_repo.all()
    assert len(orders) == 1
    assert orders[0].status == OrderStatusEnum.CANCELLED


async def test_create_order_idempotent_does_not_call_payments_twice(
    uow_factory, catalog, payments
):
    """Fast-path идемпотентности: второй вызов не доходит до Payments."""
    usecase = CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        payment_callback_url="http://x",
    )
    dto = OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1")
    await usecase(dto)
    await usecase(dto)

    assert len(payments.calls) == 1
