from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class OutboxEvent:
    """Событие, готовое к публикации в Kafka."""

    id: UUID
    topic: str
    event_type: str
    key: str
    payload: dict[str, Any]
    idempotency_key: str
    created_at: datetime


class OutboxRepository(ABC):
    """Транзакционный репозиторий outbox-событий."""

    @abstractmethod
    async def add(
        self,
        topic: str,
        event_type: str,
        key: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> UUID:
        """Сохранить событие в outbox (в текущей транзакции UoW)."""

    @abstractmethod
    async def fetch_batch(self, limit: int) -> list[OutboxEvent]:
        """Забрать пачку неопубликованных событий с блокировкой строк."""

    @abstractmethod
    async def mark_published(self, event_id: UUID) -> None:
        """Пометить событие опубликованным (published_at = now)."""


class EventPublisher(Protocol):
    """Абстракция Kafka producer."""

    async def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        """Опубликовать сообщение. Бросает при ошибке транспорта."""
