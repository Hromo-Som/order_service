from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.repositories import OrderRepository
from src.domain.entities import Order
from src.infrastructure.persistence.models import OrderORM


class SQLAlchemyRepository(OrderRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, order: Order) -> Order:
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
        await self._session.flush()
        return order

    async def get_by_id(self, order_id: UUID) -> Order | None:
        model = await self._session.get(OrderORM, order_id)
        return self._to_entity(model) if model else None

    async def get_by_idempotency_key(self, idempotency_key: str) -> Order | None:
        result = await self._session.execute(
            select(OrderORM).where(OrderORM.idempotency_key == idempotency_key)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    @staticmethod
    def _to_entity(model: OrderORM) -> Order:
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
