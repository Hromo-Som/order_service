from typing import Annotated

from fastapi import Depends, Request
from src.application.ports.catalog import CatalogClient
from src.application.usecases.create_order import CreateOrderUseCase
from src.application.usecases.get_order import GetOrderUseCase
from src.infrastructure.persistence.uow import UnitOfWork


def get_uow_factory(request: Request) -> UnitOfWork:
    return request.app.state.uow_factory


def get_catalog_client(request: Request) -> CatalogClient:
    return request.app.state.catalog_client


CatalogClientDep = Annotated[CatalogClient, Depends(get_catalog_client)]
UnitOfWorkDep = Annotated[UnitOfWork, Depends(get_uow_factory)]


def get_create_order_usecase(
    uow_factory: UnitOfWorkDep, catalog_client: CatalogClientDep
) -> CreateOrderUseCase:
    return CreateOrderUseCase(uow_factory, catalog_client)


def get_get_order_usecase(uow_factory: UnitOfWorkDep) -> GetOrderUseCase:
    return GetOrderUseCase(uow_factory)
