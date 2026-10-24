from enum import StrEnum


class OrderStatusEnum(StrEnum):
    """Статус заказа в жизненном цикле."""

    NEW = "NEW"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"
