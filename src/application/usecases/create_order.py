from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from src.application.ports.catalog import CatalogClient
from src.application.ports.uow import UnitOfWorkFactory
from src.domain.entities import Order
from src.domain.exceptions import InsufficientStockError


class OrderDTO(BaseModel):
    """DTO для входных данных."""

    user_id: str
    item_id: str
    quantity: int
    idempotency_key: str


class CreateOrderUseCase:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, catalog_client: CatalogClient
    ) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog_client

    async def __call__(self, order: OrderDTO) -> Order:
        try:
            return await self._create(order)
        except IntegrityError:
            async with self._uow_factory() as uow:
                existing = await uow.orders.get_by_idempotency_key(
                    order.idempotency_key
                )
            if existing is not None:
                return existing
            raise

    async def _create(self, order_dto: OrderDTO) -> Order:
        async with self._uow_factory() as uow:
            existing = await uow.orders.get_by_idempotency_key(
                order_dto.idempotency_key
            )
            if existing is not None:
                return existing

            item = await self._catalog.get_item(order_dto.item_id)
            if item.available_qty < order_dto.quantity:
                raise InsufficientStockError(
                    order_dto.item_id, order_dto.quantity, item.available_qty
                )

            order = Order.create(
                order_dto.user_id,
                order_dto.item_id,
                order_dto.quantity,
                order_dto.idempotency_key,
            )

            await uow.orders.add(order)
            await uow.commit()
            return order
