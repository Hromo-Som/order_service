import logging
from contextlib import asynccontextmanager

import httpx
from fastapi.responses import JSONResponse

from fastapi import FastAPI, Request, status
from src.infrastructure.http.catalog import HttpCatalogClient
from src.infrastructure.http.payments import HttpPaymentsClient
from src.infrastructure.persistence.database import (
    Base,
    create_engine,
    create_session_factory,
)
from src.infrastructure.persistence.uow import UnitOfWork
from src.presentation.api.routes import orders
from src.settings import Settings

logger = logging.getLogger(__name__)


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
        app.state.payments_client = HttpPaymentsClient(
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

    @app.exception_handler(httpx.HTTPStatusError)
    async def _httpx_status(
        request: Request, exc: httpx.HTTPStatusError
    ) -> JSONResponse:
        logger.error(
            "Upstream %s %s → %s",
            exc.request.method,
            exc.request.url,
            exc.response.status_code,
        )
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "Внешний сервис вернул ошибку"},
        )

    @app.exception_handler(httpx.RequestError)
    async def _httpx_request(request: Request, exc: httpx.RequestError) -> JSONResponse:
        logger.error(
            "Upstream unreachable: %s", exc.request.url if exc.request else "?"
        )
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "Внешний сервис недоступен"},
        )

    @app.get("/healthz", tags=["health"])
    async def healthz():
        return {"status": "ok"}

    return app
