from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from src.application.usecases.create_order import CreateOrderUseCase, OrderDTO
from src.application.usecases.get_order import GetOrderUseCase
from src.domain.exceptions import (
    InsufficientStockError,
    ItemNotFoundError,
    OrderNotFoundError,
)
from src.presentation.api.dependencies import (
    get_create_order_usecase,
    get_get_order_usecase,
)
from src.presentation.api.schemas import CreateOrderRequest, OrderResponse

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=OrderResponse)
async def create_order(
    body: CreateOrderRequest,
    usecase: Annotated[CreateOrderUseCase, Depends(get_create_order_usecase)],
) -> OrderResponse:
    try:
        order = await usecase(
            OrderDTO(
                user_id=body.user_id,
                item_id=body.item_id,
                quantity=body.quantity,
                idempotency_key=body.idempotency_key,
            )
        )
    except ItemNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e

    return OrderResponse.from_entity(order)


@router.get("/{order_id}", status_code=status.HTTP_200_OK, response_model=OrderResponse)
async def get_order(
    order_id: UUID, usecase: Annotated[GetOrderUseCase, Depends(get_get_order_usecase)]
) -> OrderResponse:
    try:
        order = await usecase(order_id)
    except OrderNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return OrderResponse.from_entity(order)
