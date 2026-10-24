import logging
from decimal import ROUND_HALF_UP, Decimal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from src.application.ports.catalog import CatalogClient
from src.application.ports.payments import PaymentsClient
from src.application.ports.uow import UnitOfWorkFactory
from src.domain.entities import Order
from src.domain.enums import OrderStatusEnum
from src.domain.exceptions import (
    DuplicateIdempotencyKeyError,
    InsufficientStockError,
    PaymentCreationFailedError,
)

logger = logging.getLogger(__name__)


class OrderDTO(BaseModel):
    """DTO для входных данных."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    idempotency_key: str = Field(min_length=1)


class CreateOrderUseCase:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        catalog_client: CatalogClient,
        payments_client: PaymentsClient,
        payment_callback_url: str,
    ) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog_client
        self._payments = payments_client
        self._payments_callback_url = payment_callback_url

    async def __call__(self, order_dto: OrderDTO) -> Order:
        try:
            return await self._create(order_dto)
        except DuplicateIdempotencyKeyError:
            async with self._uow_factory() as uow:
                existing = await uow.orders.get_by_idempotency_key(
                    order_dto.idempotency_key
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

        amount = (Decimal(item.price) * order.quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        try:
            await self._payments.create_payment(
                order_id=str(order.id),
                amount=amount,
                callback_url=self._payments_callback_url,
                idempotency_key=f"{order.id}:payment",
            )
        except httpx.HTTPError as e:
            logger.exception("Ошибка создания платежа для заказа %s — отмена", order.id)
            async with self._uow_factory() as uow:
                fresh = await uow.orders.get_by_id_for_update(order.id)
                if fresh is not None and fresh.status == OrderStatusEnum.NEW:
                    fresh.cancel()
                    await uow.orders.update(fresh)
                else:
                    logger.info(
                        "Платёж упал с ошибкой, но заказ %s уже в статусе %s — не отменяем",
                        order.id,
                        fresh.status if fresh else "unknown",
                    )
                await uow.commit()
            raise PaymentCreationFailedError(order.id, str(e)) from e

        return order
