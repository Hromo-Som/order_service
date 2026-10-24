from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс SQLAlchemy-моделей."""


def create_engine(database_url: str) -> AsyncEngine:
    """Создать async-движок SQLAlchemy."""
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Создать фабрику async-сессий."""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
