from contextlib import AbstractAsyncContextManager
from typing import Protocol

from src.application.ports.repositories import OrderRepository


class UnitOfWorkContext(Protocol):
    """Транзакционный контекст Unit of Work.
    То, что видит use case внутри `async with uow_factory() as uow:`."""

    @property
    def orders(self) -> OrderRepository:
        """Репозиторий заказов в текущей транзакции."""
        ...

    async def commit(self) -> None:
        """Зафиксировать транзакцию."""


class UnitOfWorkFactory(Protocol):
    """Фабрика UoW — вызывается как контекстный менеджер."""

    def __call__(self) -> AbstractAsyncContextManager[UnitOfWorkContext]:
        """Открыть новую транзакцию и вернуть контекст."""
        ...
