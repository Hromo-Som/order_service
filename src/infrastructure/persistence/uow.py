from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.persistence.repositories import SQLAlchemyRepository


class UnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def __call__(self):
        async with self._session_factory() as session:
            try:
                yield _UnitOfWorkImplementation(session)
                await session.rollback()
            except Exception:
                await session.rollback()
                raise


class _UnitOfWorkImplementation:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._orders = SQLAlchemyRepository(session)

    @property
    def orders(self) -> SQLAlchemyRepository:
        return self._orders

    async def commit(self) -> None:
        await self._session.commit()
