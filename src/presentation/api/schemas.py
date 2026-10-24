from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.application.usecases.handle_payment_callback import PaymentCallbackStatus
from src.domain.entities import Order
from src.domain.enums import OrderStatusEnum


class CreateOrderRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=255)
    quantity: int = Field(..., gt=0)
    item_id: str = Field(..., min_length=1, max_length=255)
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class OrderResponse(BaseModel):
    id: UUID
    user_id: str
    item_id: str
    quantity: int
    status: OrderStatusEnum
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, order: Order) -> OrderResponse:
        return cls(
            id=order.id,
            user_id=order.user_id,
            item_id=order.item_id,
            quantity=order.quantity,
            status=order.status,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )


class PaymentCallbackRequest(BaseModel):
    payment_id: str = Field(..., min_length=1)
    order_id: UUID
    status: PaymentCallbackStatus
    amount: str = Field(..., min_length=1)
    error_message: str | None = None
