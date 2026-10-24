import logging

from src.application.ports.uow import UnitOfWorkFactory
from src.domain.entities import Order
from src.domain.enums import OrderStatusEnum
from src.domain.events import ShipmentEvent
from src.domain.exceptions import InvalidOrderTransitionError

logger = logging.getLogger(__name__)


class HandleShipmentEventUseCase:
    """Применяет order.shipped / order.cancelled к заказу."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, event: ShipmentEvent) -> None:
        async with self._uow_factory() as uow:
            is_new = await uow.processed_events.try_mark_processed(event.dedup_key)
            if not is_new:
                logger.info(
                    "Дупликат shipment event проигнорирован: %s", event.dedup_key
                )
                await uow.commit()
                return

            order = await uow.orders.get_by_id_for_update(event.order_id)
            if order is None:
                logger.warning(
                    "Shipment event для неизвестного заказа: %s", event.order_id
                )
                await uow.commit()
                return
            previous = order.status
            if event.event_type == "order.shipped":
                self._handle_shipped(order, event)
            elif event.event_type == "order.cancelled":
                self._handle_cancelled(order, event)
            else:
                logger.warning(
                    "Неизвестный тип shipment event %r для заказа %s",
                    event.event_type,
                    order.id,
                )
            if previous != order.status:
                await uow.orders.update(order)
                logger.info(
                    "Заказ %s: %s → %s (event=%s)",
                    order.id,
                    previous,
                    order.status,
                    event.event_type,
                )

    @staticmethod
    def _handle_shipped(order: Order, event: ShipmentEvent) -> None:
        """Применить order.shipped."""
        if order.status == OrderStatusEnum.PAID:
            order.ship()
        elif order.status == OrderStatusEnum.SHIPPED:
            logger.info("Заказ %s уже доставлен", order.id)
        else:
            logger.warning(
                "order.shipped для заказа %s имеет неизвестный статус %s",
                order.id,
                order.status,
            )

    @staticmethod
    def _handle_cancelled(order: Order, event: ShipmentEvent) -> None:
        """Применить order.cancelled."""
        if order.status in (OrderStatusEnum.NEW, OrderStatusEnum.PAID):
            logger.info(
                "Отмена заказа %s по shipment event: %s",
                order.id,
                event.reason,
            )
            try:
                order.cancel()
            except InvalidOrderTransitionError as e:
                logger.warning("Невалидная транзакция для cancelled: %s", e)
        elif order.status == OrderStatusEnum.CANCELLED:
            logger.info("Заказ %s уже отменен", order.id)
        else:
            logger.warning(
                "order.cancelled для доставленного заказа %s — игнорирование", order.id
            )
