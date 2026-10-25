from uuid import uuid4

from src.application.usecases.create_order import CreateOrderUseCase, OrderDTO
from src.application.usecases.handle_payment_callback import (
    HandlePaymentCallbackUseCase,
    PaymentCallbackDTO,
)
from src.application.usecases.handle_shipment_event import (
    HandleShipmentEventUseCase,
)
from src.domain.enums import OrderStatusEnum
from src.domain.events import ShipmentEvent


async def _create_paid_order(uow_factory, catalog, payments, notification_service):
    """Хелпер: создаёт заказ и переводит в PAID через callback."""
    order = await CreateOrderUseCase(
        uow_factory, catalog, payments, notification_service, "http://x"
    )(OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1"))
    await HandlePaymentCallbackUseCase(uow_factory, notification_service)(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order.id,
            status="succeeded",
            amount="100.00",
        )
    )
    return order.id


async def test_shipped_paid_to_shipped(
    uow_factory, catalog, payments, notification_service, order_repo
):
    order_id = await _create_paid_order(
        uow_factory, catalog, payments, notification_service
    )

    await HandleShipmentEventUseCase(uow_factory, notification_service)(
        ShipmentEvent(
            event_type="order.shipped",
            order_id=order_id,
            item_id="item-1",
            quantity=1,
            shipment_id="s1",
        )
    )

    async with uow_factory() as uow:
        order = await uow.orders.get_by_id(order_id)
    assert order.status == OrderStatusEnum.SHIPPED


async def test_shipped_from_new_is_ignored(
    uow_factory, catalog, payments, notification_service
):
    """order.shipped на NEW (не оплачен) — не переводим в SHIPPED."""
    order = await CreateOrderUseCase(
        uow_factory, catalog, payments, notification_service, "http://x"
    )(OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1"))

    await HandleShipmentEventUseCase(uow_factory, notification_service)(
        ShipmentEvent(
            event_type="order.shipped",
            order_id=order.id,
            item_id="item-1",
            quantity=1,
            shipment_id="s1",
        )
    )

    async with uow_factory() as uow:
        fetched = await uow.orders.get_by_id(order.id)
    assert fetched.status == OrderStatusEnum.NEW


async def test_cancelled_paid_to_cancelled(
    uow_factory, catalog, payments, notification_service
):
    order_id = await _create_paid_order(
        uow_factory, catalog, payments, notification_service
    )

    await HandleShipmentEventUseCase(uow_factory, notification_service)(
        ShipmentEvent(
            event_type="order.cancelled",
            order_id=order_id,
            item_id="item-1",
            quantity=1,
            reason="Insufficient stock",
        )
    )

    async with uow_factory() as uow:
        order = await uow.orders.get_by_id(order_id)
    assert order.status == OrderStatusEnum.CANCELLED


async def test_cancelled_from_new_to_cancelled(
    uow_factory, catalog, payments, notification_service
):
    """order.cancelled на NEW — тоже отмена: Payments отказал → shipping
    тоже получил отказ, отправляет cancelled, статус должен стать CANCELLED.
    """
    order = await CreateOrderUseCase(
        uow_factory, catalog, payments, notification_service, "http://x"
    )(OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1"))

    await HandleShipmentEventUseCase(uow_factory, notification_service)(
        ShipmentEvent(
            event_type="order.cancelled",
            order_id=order.id,
            item_id="item-1",
            quantity=1,
            reason="Insufficient stock",
        )
    )

    async with uow_factory() as uow:
        fetched = await uow.orders.get_by_id(order.id)
    assert fetched.status == OrderStatusEnum.CANCELLED


async def test_shipped_cancelled_is_ignored(
    uow_factory, catalog, payments, notification_service
):
    """order.cancelled на SHIPPED — нельзя отменить отгруженный заказ."""
    order_id = await _create_paid_order(
        uow_factory, catalog, payments, notification_service
    )
    handler = HandleShipmentEventUseCase(uow_factory, notification_service)

    await handler(
        ShipmentEvent("order.shipped", order_id, "item-1", 1, shipment_id="s")
    )
    await handler(
        ShipmentEvent("order.cancelled", order_id, "item-1", 1, reason="Late cancel")
    )

    async with uow_factory() as uow:
        order = await uow.orders.get_by_id(order_id)
    assert order.status == OrderStatusEnum.SHIPPED


async def test_duplicate_shipped_is_noop(
    uow_factory, catalog, payments, notification_service, processed_events
):
    """Повторная доставка того же order.shipped — inbox блокирует."""
    order_id = await _create_paid_order(
        uow_factory, catalog, payments, notification_service
    )
    handler = HandleShipmentEventUseCase(uow_factory, notification_service)
    event = ShipmentEvent("order.shipped", order_id, "item-1", 1, shipment_id="s")

    await handler(event)
    await handler(event)

    async with uow_factory() as uow:
        order = await uow.orders.get_by_id(order_id)
    assert order.status == OrderStatusEnum.SHIPPED
    assert len(processed_events.all()) == 1


async def test_unknown_order_records_inbox_and_returns(
    uow_factory, notification_service, processed_events
):
    """Неизвестный заказ: inbox записывается, событие не ретраится."""
    handler = HandleShipmentEventUseCase(uow_factory, notification_service)
    ghost_id = uuid4()

    await handler(
        ShipmentEvent("order.shipped", ghost_id, "item-1", 1, shipment_id="s")
    )

    assert f"order.shipped:{ghost_id}" in processed_events.all()


async def test_unknown_event_type_is_logged_not_raised(
    uow_factory, catalog, payments, notification_service, processed_events
):
    """Неизвестный event_type (например, order.refunded) — лог, не падение."""
    order_id = await _create_paid_order(
        uow_factory, catalog, payments, notification_service
    )
    handler = HandleShipmentEventUseCase(uow_factory, notification_service)

    await handler(ShipmentEvent("order.refunded", order_id, "item-1", 1))

    async with uow_factory() as uow:
        order = await uow.orders.get_by_id(order_id)
    assert order.status == OrderStatusEnum.PAID
    assert len(processed_events.all()) == 1


async def test_shipped_sends_notification(
    uow_factory, catalog, payments, notifications, notification_service
):
    order_id = await _create_paid_order(
        uow_factory,
        catalog,
        payments,
        notification_service,
    )

    await HandleShipmentEventUseCase(uow_factory, notification_service)(
        ShipmentEvent(
            event_type="order.shipped",
            order_id=order_id,
            item_id="item-1",
            quantity=1,
            shipment_id="s1",
        )
    )

    shipped = notifications.by_status("SHIPPED")
    assert len(shipped) == 1
    assert shipped[0]["reference_id"] == str(order_id)
    assert "доставку" in shipped[0]["message"]


async def test_cancelled_sends_notification_with_reason(
    uow_factory, catalog, payments, notifications, notification_service
):
    order_id = await _create_paid_order(
        uow_factory,
        catalog,
        payments,
        notification_service,
    )

    await HandleShipmentEventUseCase(uow_factory, notification_service)(
        ShipmentEvent(
            event_type="order.cancelled",
            order_id=order_id,
            item_id="item-1",
            quantity=1,
            reason="Insufficient stock",
        )
    )

    cancelled = notifications.by_status("CANCELLED")
    assert len(cancelled) == 1
    assert "Insufficient stock" in cancelled[0]["message"]


async def test_duplicate_shipped_does_not_duplicate_notification(
    uow_factory, catalog, payments, notifications, notification_service
):
    """Повторная доставка order.shipped → только одна SHIPPED notification."""
    order_id = await _create_paid_order(
        uow_factory,
        catalog,
        payments,
        notification_service,
    )
    handler = HandleShipmentEventUseCase(uow_factory, notification_service)
    event = ShipmentEvent(
        event_type="order.shipped",
        order_id=order_id,
        item_id="item-1",
        quantity=1,
        shipment_id="s1",
    )

    await handler(event)
    await handler(event)

    assert len(notifications.by_status("SHIPPED")) == 1


async def test_shipped_from_new_does_not_send_notification(
    uow_factory, catalog, payments, notifications, notification_service
):
    """order.shipped на NEW → ignore, без SHIPPED-уведомления."""
    order = await CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        notification_service,
        "http://x",
    )(OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1"))

    await HandleShipmentEventUseCase(uow_factory, notification_service)(
        ShipmentEvent(
            event_type="order.shipped",
            order_id=order.id,
            item_id="item-1",
            quantity=1,
            shipment_id="s1",
        )
    )

    assert notifications.by_status("SHIPPED") == []


async def test_shipped_notification_failure_does_not_break_status(
    uow_factory, catalog, payments, notifications, notification_service
):
    """Сбой notifications не откатывает status = SHIPPED."""
    order_id = await _create_paid_order(
        uow_factory,
        catalog,
        payments,
        notification_service,
    )

    notifications.fail_next = True
    await HandleShipmentEventUseCase(uow_factory, notification_service)(
        ShipmentEvent(
            event_type="order.shipped",
            order_id=order_id,
            item_id="item-1",
            quantity=1,
            shipment_id="s1",
        )
    )

    async with uow_factory() as uow:
        order = await uow.orders.get_by_id(order_id)
    assert order.status == OrderStatusEnum.SHIPPED
