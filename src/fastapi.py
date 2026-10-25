import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi.responses import JSONResponse

from fastapi import FastAPI, Request, status
from src.application.ports.errors import UpstreamServiceError
from src.infrastructure.http.catalog import HttpCatalogClient
from src.infrastructure.http.notifications import HttpNotificationsClient
from src.infrastructure.http.payments import HttpPaymentsClient
from src.infrastructure.persistence.database import (
    create_engine,
    create_session_factory,
)
from src.infrastructure.persistence.migrations import run_migrations
from src.infrastructure.persistence.uow import UnitOfWork
from src.presentation.api.routes import orders
from src.settings import Settings

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Фабрика FastAPI-приложения — composition root."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )

    settings = Settings()

    logging.getLogger().setLevel(settings.log_level.upper())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Управление ресурсами приложения: startup и graceful shutdown."""
        await asyncio.to_thread(run_migrations, settings.database_url)

        engine = create_engine(settings.database_url)
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
        app.state.notifications_client = HttpNotificationsClient(
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

    @app.exception_handler(UpstreamServiceError)
    async def _upstream_error(
        request: Request, exc: UpstreamServiceError
    ) -> JSONResponse:
        logger.error("Upstream %s unreachable: %s", exc.service_name, exc.reason)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": f"Сервис {exc.service_name} недоступен"},
        )

    @app.get("/healthz", tags=["health"])
    async def healthz():
        """Liveness/readiness probe."""
        return {"status": "ok"}

    return app
