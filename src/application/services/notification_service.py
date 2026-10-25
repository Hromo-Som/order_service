import asyncio
import logging
from uuid import UUID

from src.application.ports.notifications import NotificationsClient
from src.application.services.notification_key import build_idempotency_key
from src.domain.enums import OrderStatusEnum

logger = logging.getLogger(__name__)


class NotificationService:
    """Отправка уведомлений пользователю о смене статуса заказа."""

    def __init__(self, client: NotificationsClient) -> None:
        self._client = client

    async def notify_new(self, order_id: UUID) -> None:
        """Уведомление о создании заказа (NEW)."""
        await self._send_safe(
            order_id,
            OrderStatusEnum.NEW,
            "NEW: Ваш заказ создан и ожидает оплаты",
        )

    async def notify_paid(self, order_id: UUID) -> None:
        """Уведомление об успешной оплате (PAID)."""
        await self._send_safe(
            order_id,
            OrderStatusEnum.PAID,
            "PAID: Ваш заказ успешно оплачен и готов к отправке",
        )

    async def notify_shipped(self, order_id: UUID) -> None:
        """Уведомление об отправке (SHIPPED)."""
        await self._send_safe(
            order_id,
            OrderStatusEnum.SHIPPED,
            "SHIPPED: Ваш заказ отправлен в доставку",
        )

    async def notify_cancelled(self, order_id: UUID, reason: str) -> None:
        """Уведомление об отмене (CANCELLED) с причиной."""
        await self._send_safe(
            order_id,
            OrderStatusEnum.CANCELLED,
            f"CANCELLED: Ваш заказ отменен. Причина: {reason}",
        )

    async def _send_safe(
        self,
        order_id: UUID,
        status: OrderStatusEnum,
        message: str,
    ) -> None:
        """Отправить уведомление, проглотив ошибку."""
        last_exc: Exception | None = None

        for attempt in range(3):
            try:
                await self._client.send(
                    message=message,
                    reference_id=str(order_id),
                    idempotency_key=build_idempotency_key(order_id, status),
                )
                return
            except Exception as e:
                last_exc = e
                if attempt < 2:
                    delay = 0.5 * (2 ** attempt)
                    logger.warning(
                        "Повтор %s отправка уведомления для заказа %s in %.1fs "
                        "(attempt %d, error: %s)",
                        status.value, order_id, delay, attempt + 1, e,
                    )
                    await asyncio.sleep(delay)

        logger.error(
            "Ошибка отправки уведомления %s для заказа %s после 3 попыток",
            status.value, order_id, exc_info=last_exc,
        )
