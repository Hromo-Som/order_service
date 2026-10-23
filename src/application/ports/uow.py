from contextlib import AbstractAsyncContextManager
from typing import Protocol

from src.application.ports.repositories import OrderRepository


class UnitOfWorkContext(Protocol):
    """То, что видит use case внутри `async with uow_factory() as uow:`."""

    @property
    def orders(self) -> OrderRepository: ...

    async def commit(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    """Фабрика UoW — вызывается как контекстный менеджер."""

    def __call__(self) -> AbstractAsyncContextManager[UnitOfWorkContext]: ...
