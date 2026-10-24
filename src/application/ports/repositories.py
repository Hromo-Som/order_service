from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities import Order


class OrderRepository(ABC):
    """Порт хранилища заказов."""

    @abstractmethod
    async def add(self, order: Order) -> Order:
        """Сохранить новый заказ."""

    @abstractmethod
    async def get_by_id(self, order_id: UUID) -> Order | None:
        """Найти заказ по идентификатору."""

    @abstractmethod
    async def get_by_idempotency_key(self, idempotency_key: str) -> Order | None:
        """Найти заказ по ключу идемпотентности."""

    @abstractmethod
    async def update(self, order: Order) -> Order:
        """Сохранить изменения существующего заказа."""

    @abstractmethod
    async def get_by_id_for_update(self, order_id: UUID) -> Order | None:
        """Найти заказ. SELECT ... FOR UPDATE — блокирует строку до конца транзакции."""
