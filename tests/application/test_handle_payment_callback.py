from uuid import UUID, uuid4

from src.application.usecases.create_order import CreateOrderUseCase, OrderDTO
from src.application.usecases.handle_payment_callback import (
    HandlePaymentCallbackUseCase,
    PaymentCallbackDTO,
)
from src.domain.enums import OrderStatusEnum


async def _create_paid_order(uow_factory, catalog, payments) -> UUID:
    """Создаёт заказ через use case, возвращает id."""
    usecase = CreateOrderUseCase(uow_factory, catalog, payments, "http://x")
    order = await usecase(
        OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1")
    )
    return order.id


async def test_callback_success_new_to_paid(uow_factory, catalog, payments):
    order_id = await _create_paid_order(uow_factory, catalog, payments)
    handler = HandlePaymentCallbackUseCase(uow_factory)

    await handler(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order_id,
            status="succeeded",
            amount="100.00",
        )
    )

    async with uow_factory() as uow:
        order = await uow.orders.get_by_id(order_id)
    assert order.status == OrderStatusEnum.PAID


async def test_callback_failure_new_to_cancelled(uow_factory, catalog, payments):
    order_id = await _create_paid_order(uow_factory, catalog, payments)
    handler = HandlePaymentCallbackUseCase(uow_factory)

    await handler(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order_id,
            status="failed",
            amount="100.00",
            error_message="Card declined",
        )
    )

    async with uow_factory() as uow:
        order = await uow.orders.get_by_id(order_id)
    assert order.status == OrderStatusEnum.CANCELLED


async def test_callback_success_idempotent(uow_factory, catalog, payments):
    """Двойной succeeded — второй no-op."""
    order_id = await _create_paid_order(uow_factory, catalog, payments)
    handler = HandlePaymentCallbackUseCase(uow_factory)
    dto = PaymentCallbackDTO(
        payment_id="p1", order_id=order_id, status="succeeded", amount="100.00"
    )

    await handler(dto)
    await handler(dto)

    async with uow_factory() as uow:
        order = await uow.orders.get_by_id(order_id)
    assert order.status == OrderStatusEnum.PAID


async def test_callback_failure_after_success_is_noop(uow_factory, catalog, payments):
    """Поздний failed после succeeded — игнорируется."""
    order_id = await _create_paid_order(uow_factory, catalog, payments)
    handler = HandlePaymentCallbackUseCase(uow_factory)

    await handler(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order_id,
            status="succeeded",
            amount="100.00",
        )
    )
    await handler(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order_id,
            status="failed",
            amount="100.00",
        )
    )

    async with uow_factory() as uow:
        order = await uow.orders.get_by_id(order_id)
    assert order.status == OrderStatusEnum.PAID


async def test_callback_success_after_cancel_is_noop(uow_factory, catalog, payments):
    """Поздний succeeded после failed → CANCELLED, не откатываем."""
    order_id = await _create_paid_order(uow_factory, catalog, payments)
    handler = HandlePaymentCallbackUseCase(uow_factory)

    await handler(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order_id,
            status="failed",
            amount="100.00",
        )
    )
    await handler(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order_id,
            status="succeeded",
            amount="100.00",
        )
    )

    async with uow_factory() as uow:
        order = await uow.orders.get_by_id(order_id)
    assert order.status == OrderStatusEnum.CANCELLED


async def test_callback_unknown_order_is_noop(uow_factory):
    handler = HandlePaymentCallbackUseCase(uow_factory)
    await handler(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=uuid4(),
            status="succeeded",
            amount="100.00",
        )
    )
