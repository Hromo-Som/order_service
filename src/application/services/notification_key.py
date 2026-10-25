from uuid import UUID

from src.domain.enums import OrderStatusEnum


def build_idempotency_key(order_id: UUID, status: OrderStatusEnum) -> str:
    """Построить idempotency_key для уведомления о статусе заказа."""
    return f"order:{order_id}:{status.value}"
