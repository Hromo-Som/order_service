from uuid import UUID

from src.application.ports.uow import UnitOfWorkFactory
from src.domain.entities import Order
from src.domain.exceptions import OrderNotFoundError


class GetOrderUseCase:
    """Сценарий получения заказа по идентификатору."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, order_id: UUID) -> Order:
        """Вернуть заказ."""
        async with self._uow_factory() as uow:
            order = await uow.orders.get_by_id(order_id)
            if order is None:
                raise OrderNotFoundError(order_id)
            return order
