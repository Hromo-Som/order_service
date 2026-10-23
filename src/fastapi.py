from contextlib import asynccontextmanager

import httpx

from fastapi import FastAPI
from src.infrastructure.http.catalog import HttpCatalogClient
from src.infrastructure.persistence.database import (
    Base,
    create_engine,
    create_session_factory,
)
from src.infrastructure.persistence.uow import UnitOfWork
from src.presentation.api.routes import orders
from src.settings import Settings


def create_app() -> FastAPI:
    settings = Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = create_session_factory(engine)
        app.state.uow_factory = UnitOfWork(session_factory)
        app.state.http_client = httpx.AsyncClient(timeout=10.0)
        app.state.catalog_client = HttpCatalogClient(
            base_url=settings.capashino_base_url,
            api_key=settings.capashino_api_token.get_secret_value(),
            client=app.state.http_client,
        )

        try:
            yield
        finally:
            await app.state.http_client.aclose()
            await engine.dispose()

    app = FastAPI(title="Order Service", lifespan=lifespan)
    app.state.settings = settings

    app.include_router(orders.router)

    @app.get("/healthz", tags=["health"])
    async def healthz():
        return {"status": "ok"}

    return app
