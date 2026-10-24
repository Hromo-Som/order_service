from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.repositories import OrderRepository
from src.domain.entities import Order
from src.domain.exceptions import DuplicateIdempotencyKeyError, OrderNotFoundError
from src.infrastructure.persistence.models import OrderORM


class SQLAlchemyRepository(OrderRepository):
    """SQLAlchemy-реализация OrderRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, order: Order) -> Order:
        """Сохранить новый заказ."""
        model = OrderORM(
            id=order.id,
            user_id=order.user_id,
            item_id=order.item_id,
            quantity=order.quantity,
            status=order.status,
            idempotency_key=order.idempotency_key,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
        self._session.add(model)
        try:
            await self._session.flush()
        except IntegrityError as e:
            if "idempotency_key" in str(e.orig):
                raise DuplicateIdempotencyKeyError(order.idempotency_key) from e
            raise
        return order

    async def get_by_id(self, order_id: UUID) -> Order | None:
        """Найти заказ по id без блокировки строки."""
        model = await self._session.get(OrderORM, order_id)
        return self._to_entity(model) if model else None

    async def get_by_idempotency_key(self, idempotency_key: str) -> Order | None:
        """Найти заказ по idempotency_key без блокировки строки."""
        result = await self._session.execute(
            select(OrderORM).where(OrderORM.idempotency_key == idempotency_key)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def update(self, order: Order) -> Order:
        """Сохранить изменения заказа в БД."""
        model = await self._session.get(OrderORM, order.id)
        if model is None:
            raise OrderNotFoundError(order.id)
        model.status = order.status
        model.updated_at = order.updated_at
        return order

    async def get_by_id_for_update(self, order_id: UUID) -> Order | None:
        """Найти заказ с блокировкой строки (SELECT ... FOR UPDATE)."""
        result = await self._session.execute(
            select(OrderORM).where(OrderORM.id == order_id).with_for_update()
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    @staticmethod
    def _to_entity(model: OrderORM) -> Order:
        """Сконвертировать ORM-модель в доменную сущность."""
        return Order(
            id=model.id,
            user_id=model.user_id,
            item_id=model.item_id,
            quantity=model.quantity,
            status=model.status,
            idempotency_key=model.idempotency_key,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
