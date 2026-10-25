from uuid import UUID, uuid4

from src.application.usecases.create_order import CreateOrderUseCase, OrderDTO
from src.application.usecases.handle_payment_callback import (
    HandlePaymentCallbackUseCase,
    PaymentCallbackDTO,
)
from src.domain.enums import OrderStatusEnum
from src.domain.events import ORDER_EVENTS_TOPIC


async def _create_new_order(
    uow_factory, catalog, payments, notification_service
) -> UUID:
    """Создаёт заказ через use case, возвращает id."""
    usecase = CreateOrderUseCase(
        uow_factory, catalog, payments, notification_service, "http://x"
    )
    order = await usecase(
        OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1")
    )
    return order.id


async def test_callback_success_new_to_paid(
    uow_factory, catalog, payments, notification_service
):
    order_id = await _create_new_order(
        uow_factory, catalog, payments, notification_service
    )
    handler = HandlePaymentCallbackUseCase(uow_factory, notification_service)

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


async def test_callback_failure_new_to_cancelled(
    uow_factory, catalog, payments, notification_service
):
    order_id = await _create_new_order(
        uow_factory, catalog, payments, notification_service
    )
    handler = HandlePaymentCallbackUseCase(uow_factory, notification_service)

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


async def test_callback_success_idempotent(
    uow_factory, catalog, payments, notification_service
):
    """Двойной succeeded — второй no-op."""
    order_id = await _create_new_order(
        uow_factory, catalog, payments, notification_service
    )
    handler = HandlePaymentCallbackUseCase(uow_factory, notification_service)
    dto = PaymentCallbackDTO(
        payment_id="p1", order_id=order_id, status="succeeded", amount="100.00"
    )

    await handler(dto)
    await handler(dto)

    async with uow_factory() as uow:
        order = await uow.orders.get_by_id(order_id)
    assert order.status == OrderStatusEnum.PAID


async def test_callback_failure_after_success_is_noop(
    uow_factory, catalog, payments, notification_service
):
    """Поздний failed после succeeded — игнорируется."""
    order_id = await _create_new_order(
        uow_factory, catalog, payments, notification_service
    )
    handler = HandlePaymentCallbackUseCase(uow_factory, notification_service)

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


async def test_callback_success_after_cancel_is_noop(
    uow_factory, catalog, payments, notification_service
):
    """Поздний succeeded после failed → CANCELLED, не откатываем."""
    order_id = await _create_new_order(
        uow_factory, catalog, payments, notification_service
    )
    handler = HandlePaymentCallbackUseCase(uow_factory, notification_service)

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


async def test_callback_unknown_order_is_noop(uow_factory, notification_service):
    handler = HandlePaymentCallbackUseCase(uow_factory, notification_service)
    await handler(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=uuid4(),
            status="succeeded",
            amount="100.00",
        )
    )


async def test_callback_success_adds_outbox_event(
    uow_factory, catalog, payments, notification_service, outbox
):
    """Успешный callback → order.paid в outbox в той же транзакции."""
    order_id = await _create_new_order(
        uow_factory, catalog, payments, notification_service
    )
    await HandlePaymentCallbackUseCase(uow_factory, notification_service)(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order_id,
            status="succeeded",
            amount="100.00",
        )
    )

    async with uow_factory() as uow:
        events = await uow.outbox.fetch_batch(10)

    assert len(events) == 1
    e = events[0]
    assert e.topic == ORDER_EVENTS_TOPIC
    assert e.event_type == "order.paid"
    assert e.key == str(order_id)
    assert e.payload["order_id"] == str(order_id)
    assert e.payload["item_id"] == "item-1"
    assert e.payload["quantity"] == 1
    assert "idempotency_key" in e.payload


async def test_callback_duplicate_success_does_not_add_second_outbox(
    uow_factory, catalog, payments, notification_service, outbox
):
    """Повторный succeeded — no-op: ни смены статуса, ни нового outbox."""
    order_id = await _create_new_order(
        uow_factory, catalog, payments, notification_service
    )
    handler = HandlePaymentCallbackUseCase(uow_factory, notification_service)
    dto = PaymentCallbackDTO(
        payment_id="p1",
        order_id=order_id,
        status="succeeded",
        amount="100.00",
    )

    await handler(dto)
    await handler(dto)

    async with uow_factory() as uow:
        events = await uow.outbox.fetch_batch(10)

    assert len(events) == 1


async def test_callback_failed_does_not_add_outbox(
    uow_factory, catalog, payments, notification_service, outbox
):
    """failed callback → CANCELLED, но БЕЗ order.paid в outbox."""
    order = await CreateOrderUseCase(
        uow_factory, catalog, payments, notification_service, "http://x"
    )(OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1"))

    await HandlePaymentCallbackUseCase(uow_factory, notification_service)(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order.id,
            status="failed",
            amount="100.00",
            error_message="Declined",
        )
    )

    async with uow_factory() as uow:
        events = await uow.outbox.fetch_batch(10)
    assert events == []


async def test_callback_success_sends_paid_notification(
    uow_factory, catalog, payments, notifications, notification_service
):
    order = await CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        notification_service,
        "http://x",
    )(OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1"))

    await HandlePaymentCallbackUseCase(uow_factory, notification_service)(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order.id,
            status="succeeded",
            amount="100.00",
        )
    )

    paid = notifications.by_status("PAID")
    assert len(paid) == 1
    assert paid[0]["reference_id"] == str(order.id)
    assert "оплачен" in paid[0]["message"]


async def test_callback_failure_sends_cancelled_notification(
    uow_factory, catalog, payments, notifications, notification_service
):
    order = await CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        notification_service,
        "http://x",
    )(OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1"))

    await HandlePaymentCallbackUseCase(uow_factory, notification_service)(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order.id,
            status="failed",
            amount="100.00",
            error_message="Card declined",
        )
    )

    cancelled = notifications.by_status("CANCELLED")
    assert len(cancelled) == 1
    assert "Card declined" in cancelled[0]["message"]


async def test_callback_duplicate_success_does_not_duplicate_paid_notification(
    uow_factory, catalog, payments, notifications, notification_service
):
    """Повторный succeeded — только одна PAID notification."""
    order = await CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        notification_service,
        "http://x",
    )(OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1"))

    handler = HandlePaymentCallbackUseCase(uow_factory, notification_service)
    dto = PaymentCallbackDTO(
        payment_id="p1",
        order_id=order.id,
        status="succeeded",
        amount="100.00",
    )

    await handler(dto)
    await handler(dto)

    assert len(notifications.by_status("PAID")) == 1


async def test_callback_late_failure_after_success_no_notification(
    uow_factory, catalog, payments, notifications, notification_service
):
    """Поздний failed после succeeded — CANCELLED-уведомление НЕ отправляется."""
    order = await CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        notification_service,
        "http://x",
    )(OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1"))

    handler = HandlePaymentCallbackUseCase(uow_factory, notification_service)
    await handler(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order.id,
            status="succeeded",
            amount="100.00",
        )
    )
    await handler(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order.id,
            status="failed",
            amount="100.00",
        )
    )

    assert len(notifications.by_status("PAID")) == 1
    assert len(notifications.by_status("CANCELLED")) == 0


async def test_callback_notification_failure_does_not_break_status_update(
    uow_factory, catalog, payments, notifications, notification_service, order_repo
):
    """Сбой notifications НЕ откатывает status = PAID."""
    order = await CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        notification_service,
        "http://x",
    )(OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1"))

    notifications.fail_next = True
    await HandlePaymentCallbackUseCase(uow_factory, notification_service)(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order.id,
            status="succeeded",
            amount="100.00",
        )
    )

    async with uow_factory() as uow:
        fetched = await uow.orders.get_by_id(order.id)
    assert fetched.status == OrderStatusEnum.PAID
