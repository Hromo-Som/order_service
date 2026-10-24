from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from src.application.usecases.create_order import OrderDTO
from src.application.usecases.handle_payment_callback import PaymentCallbackDTO
from src.domain.exceptions import (
    InsufficientStockError,
    ItemNotFoundError,
    OrderNotFoundError,
    PaymentCreationFailedError,
)
from src.presentation.api.dependencies import (
    CreateOrderUseCaseDep,
    GetOrderUseCaseDep,
    HandlePaymentCallbackUseCaseDep,
)
from src.presentation.api.schemas import (
    CreateOrderRequest,
    OrderResponse,
    PaymentCallbackRequest,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=OrderResponse)
async def create_order(
    body: CreateOrderRequest,
    usecase: CreateOrderUseCaseDep,
) -> OrderResponse:
    """Создать заказ."""
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
        ) from None
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from None
    except PaymentCreationFailedError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    return OrderResponse.from_entity(order)


@router.post("/payment-callback", status_code=status.HTTP_200_OK)
async def payment_callback(
    body: PaymentCallbackRequest,
    usecase: HandlePaymentCallbackUseCaseDep,
) -> dict[str, str]:
    """Callback от Payments Service."""
    await usecase(
        PaymentCallbackDTO(
            payment_id=body.payment_id,
            order_id=body.order_id,
            status=body.status,
            amount=body.amount,
            error_message=body.error_message,
        )
    )
    return {"status": "ok"}


@router.get("/{order_id}", status_code=status.HTTP_200_OK, response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    usecase: GetOrderUseCaseDep,
) -> OrderResponse:
    """Получить заказ по идентификатору."""
    try:
        order = await usecase(order_id)
    except OrderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from None
    return OrderResponse.from_entity(order)
