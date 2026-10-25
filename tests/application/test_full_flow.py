from src.application.usecases.create_order import CreateOrderUseCase, OrderDTO
from src.application.usecases.handle_payment_callback import (
    HandlePaymentCallbackUseCase,
    PaymentCallbackDTO,
)
from src.application.usecases.handle_shipment_event import HandleShipmentEventUseCase
from src.domain.enums import OrderStatusEnum
from src.domain.events import ShipmentEvent


async def test_full_order_flow_emits_three_notifications(
    uow_factory,
    catalog,
    payments,
    notifications,
    notification_service,
    order_repo,
):
    order = await CreateOrderUseCase(
        uow_factory,
        catalog,
        payments,
        notification_service,
        "http://x",
    )(OrderDTO(user_id="u1", item_id="item-1", quantity=1, idempotency_key="k1"))
    assert order.status == OrderStatusEnum.NEW

    await HandlePaymentCallbackUseCase(uow_factory, notification_service)(
        PaymentCallbackDTO(
            payment_id="p1",
            order_id=order.id,
            status="succeeded",
            amount="100.00",
        )
    )

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
        final = await uow.orders.get_by_id(order.id)
    assert final.status == OrderStatusEnum.SHIPPED

    assert len(notifications.sent) == 3
    assert [n["idempotency_key"].rsplit(":", 1)[-1] for n in notifications.sent] == [
        "NEW",
        "PAID",
        "SHIPPED",
    ]
    for n in notifications.sent:
        assert n["reference_id"] == str(order.id)


async def test_full_order_cancelled_flow_emits_two_notifications(
    uow_factory,
    catalog,
    payments,
    notifications,
    notification_service,
):
    """Создание + payment failed → NEW + CANCELLED. Нет PAID/SHIPPED."""
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

    async with uow_factory() as uow:
        final = await uow.orders.get_by_id(order.id)
    assert final.status == OrderStatusEnum.CANCELLED

    assert len(notifications.sent) == 2
    assert [n["idempotency_key"].rsplit(":", 1)[-1] for n in notifications.sent] == [
        "NEW",
        "CANCELLED",
    ]
