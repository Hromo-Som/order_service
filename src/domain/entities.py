from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.domain.enums import OrderStatusEnum
from src.domain.exceptions import InvalidOrderTransitionError


class Order(BaseModel):
    """Заказ — корневая сущность агрегата."""

    id: UUID
    user_id: str
    item_id: str
    quantity: int = Field(gt=0)
    status: OrderStatusEnum
    idempotency_key: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls, user_id: str, item_id: str, quantity: int, idempotency_key: str
    ) -> Order:
        """Создать новый заказ в статусе NEW."""
        now = datetime.now(UTC)
        return cls(
            id=uuid4(),
            user_id=user_id,
            item_id=item_id,
            quantity=quantity,
            status=OrderStatusEnum.NEW,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )

    def pay(self) -> None:
        """Перевести заказ в PAID."""
        if self.status != OrderStatusEnum.NEW:
            raise InvalidOrderTransitionError(
                self.id, self.status, OrderStatusEnum.PAID
            )
        self.status = OrderStatusEnum.PAID
        self.updated_at = datetime.now(UTC)

    def ship(self) -> None:
        """Перевести заказ в SHIPPED."""
        if self.status != OrderStatusEnum.PAID:
            raise InvalidOrderTransitionError(
                self.id, self.status, OrderStatusEnum.SHIPPED
            )
        self.status = OrderStatusEnum.SHIPPED
        self.updated_at = datetime.now(UTC)

    def cancel(self) -> None:
        """Перевести заказ в CANCELLED."""
        if self.status not in (OrderStatusEnum.NEW, OrderStatusEnum.PAID):
            raise InvalidOrderTransitionError(
                self.id, self.status, OrderStatusEnum.CANCELLED
            )
        self.status = OrderStatusEnum.CANCELLED
        self.updated_at = datetime.now(UTC)
