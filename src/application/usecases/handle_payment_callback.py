import logging
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from src.application.ports.uow import UnitOfWorkFactory
from src.domain.enums import OrderStatusEnum
from src.domain.events import ORDER_EVENTS_TOPIC, OrderPaidEvent

logger = logging.getLogger(__name__)

PaymentCallbackStatus = Literal["succeeded", "failed"]


@dataclass(frozen=True)
class PaymentCallbackDTO:
    """Данные callback'а от Payments Service."""

    payment_id: str
    order_id: UUID
    status: PaymentCallbackStatus
    amount: str
    error_message: str | None = None


class HandlePaymentCallbackUseCase:
    """Сценарий обработки callback'а от Payments Service."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, pc_dto: PaymentCallbackDTO) -> None:
        """Обработать callback."""
        async with self._uow_factory() as uow:
            order = await uow.orders.get_by_id_for_update(pc_dto.order_id)

            if order is None:
                logger.warning(
                    "Payment callback для неизвестного заказа: payment_id=%s order_id=%s",
                    pc_dto.payment_id,
                    pc_dto.order_id,
                )
                return

            previous = order.status

            if pc_dto.status == "succeeded":
                if order.status == OrderStatusEnum.NEW:
                    order.pay()
                    await uow.orders.update(order)
                    paid_event = OrderPaidEvent(
                        order_id=order.id,
                        item_id=order.item_id,
                        quantity=order.quantity,
                        idempotency_key=uuid4(),
                    )
                    await uow.outbox.add(
                        topic=ORDER_EVENTS_TOPIC,
                        event_type=paid_event.event_type,
                        key=str(order.id),
                        payload=paid_event.to_payload(),
                        idempotency_key=str(paid_event.idempotency_key),
                    )
                elif order.status in (OrderStatusEnum.PAID, OrderStatusEnum.SHIPPED):
                    logger.info(
                        "Повторный success callback: order=%s already %s",
                        order.id,
                        order.status,
                    )
                elif order.status == OrderStatusEnum.CANCELLED:
                    logger.warning(
                        "Поздний success callback для отмененного заказа %s (payment=%s)",
                        order.id,
                        pc_dto.payment_id,
                    )
            elif pc_dto.status == "failed":
                if order.status == OrderStatusEnum.NEW:
                    logger.info(
                        "Отмена заказа %s по callback (payment=%s): %s",
                        order.id,
                        pc_dto.payment_id,
                        pc_dto.error_message,
                    )
                    order.cancel()
                    await uow.orders.update(order)
                elif order.status in (OrderStatusEnum.PAID, OrderStatusEnum.SHIPPED):
                    logger.warning(
                        "Поздний failure callback для оплаченного заказа %s (payment=%s): %s",
                        order.id,
                        pc_dto.payment_id,
                        pc_dto.error_message,
                    )
                elif order.status == OrderStatusEnum.CANCELLED:
                    logger.info("Повторный failure callback для %s", order.id)
            else:
                logger.warning(
                    "Неизвестный статус платежа %r для заказа %s",
                    pc_dto.status,
                    order.id,
                )

            await uow.commit()

            if previous != order.status:
                logger.info(
                    "Заказ %s статус: %s → %s (payment=%s)",
                    order.id,
                    previous,
                    order.status,
                    pc_dto.payment_id,
                )
