from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.persistence.repositories import (
    SQLAlchemyOutboxRepository,
    SQLAlchemyProcessedEventsRepository,
    SQLAlchemyRepository,
)


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
        self._outbox = SQLAlchemyOutboxRepository(session)
        self._processed_events = SQLAlchemyProcessedEventsRepository(session)

    @property
    def orders(self) -> SQLAlchemyRepository:
        """Репозиторий заказов в текущей транзакции."""
        return self._orders

    @property
    def outbox(self) -> SQLAlchemyOutboxRepository:
        """Outbox репозиторий в текущей транзакции."""
        return self._outbox

    @property
    def processed_events(self) -> SQLAlchemyProcessedEventsRepository:
        """Репозиторий обработанных событий в текущей транзакции."""
        return self._processed_events

    async def commit(self) -> None:
        """Зафиксировать транзакцию."""
        await self._session.commit()
