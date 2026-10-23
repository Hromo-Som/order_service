from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.entities import OrderStatusEnum
from src.infrastructure.persistence.database import Base


class OrderORM(Base):
    __tablename__ = "orders"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    item_id: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int]
    status: Mapped[OrderStatusEnum] = mapped_column(
        SAEnum(OrderStatusEnum, name="order_status")
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
