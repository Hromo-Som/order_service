from typing import Annotated

from fastapi import Depends, Request
from src.application.ports.catalog import CatalogClient
from src.application.ports.payments import PaymentsClient
from src.application.usecases.create_order import CreateOrderUseCase
from src.application.usecases.get_order import GetOrderUseCase
from src.application.usecases.handle_payment_callback import (
    HandlePaymentCallbackUseCase,
)
from src.infrastructure.persistence.uow import UnitOfWork


def get_uow_factory(request: Request) -> UnitOfWork:
    return request.app.state.uow_factory


def get_catalog_client(request: Request) -> CatalogClient:
    return request.app.state.catalog_client


def get_payments_client(request: Request) -> PaymentsClient:
    return request.app.state.payments_client


def get_payment_callback_url(request: Request) -> str:
    return request.app.state.settings.payment_callback_url


CatalogClientDep = Annotated[CatalogClient, Depends(get_catalog_client)]
UnitOfWorkDep = Annotated[UnitOfWork, Depends(get_uow_factory)]
PaymentsClientDep = Annotated[PaymentsClient, Depends(get_payments_client)]
PaymentCallbackUrlDep = Annotated[str, Depends(get_payment_callback_url)]


def get_create_order_usecase(
    uow_factory: UnitOfWorkDep,
    catalog_client: CatalogClientDep,
    payments_client: PaymentsClientDep,
    payment_callback_url: PaymentCallbackUrlDep,
) -> CreateOrderUseCase:
    return CreateOrderUseCase(
        uow_factory, catalog_client, payments_client, payment_callback_url
    )


def get_get_order_usecase(uow_factory: UnitOfWorkDep) -> GetOrderUseCase:
    return GetOrderUseCase(uow_factory)


def get_handle_payment_callback_usecase(
    uow_factory: UnitOfWorkDep,
) -> HandlePaymentCallbackUseCase:
    return HandlePaymentCallbackUseCase(uow_factory)


CreateOrderUseCaseDep = Annotated[CreateOrderUseCase, Depends(get_create_order_usecase)]
GetOrderUseCaseDep = Annotated[GetOrderUseCase, Depends(get_get_order_usecase)]
HandlePaymentCallbackUseCaseDep = Annotated[
    HandlePaymentCallbackUseCase, Depends(get_handle_payment_callback_usecase)
]
