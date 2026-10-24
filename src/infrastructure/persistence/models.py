from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.entities import OrderStatusEnum
from src.infrastructure.persistence.database import Base


class OrderORM(Base):
    """ORM-модель таблицы orders."""

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


class OutboxEventORM(Base):
    """Outbox-таблица: исходящие события до публикации в Kafka."""

    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(100))
    key: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSONB)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_outbox_events_unpublished",
            "published_at",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )


class ProcessedEventORM(Base):
    """Inbox-таблица: обработанные входящие события (дедупликация)."""

    __tablename__ = "processed_events"

    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
    )
