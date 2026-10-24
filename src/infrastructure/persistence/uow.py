from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.persistence.repositories import SQLAlchemyRepository


class UnitOfWork:
    """Реализация UnitOfWorkFactory через сессию SQLAlchemy."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def __call__(self):
        """Открыть транзакцию и вернуть контекст UoW."""
        async with self._session_factory() as session:
            try:
                yield _UnitOfWorkImplementation(session)
                await session.rollback()
            except Exception:
                await session.rollback()
                raise


class _UnitOfWorkImplementation:
    """То, что видит use case внутри `async with uow_factory() as uow:`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._orders = SQLAlchemyRepository(session)

    @property
    def orders(self) -> SQLAlchemyRepository:
        """Репозиторий заказов в текущей транзакции."""
        return self._orders

    async def commit(self) -> None:
        """Зафиксировать транзакцию."""
        await self._session.commit()
