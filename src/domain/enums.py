from enum import StrEnum


class OrderStatusEnum(StrEnum):
    NEW = "NEW"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"
