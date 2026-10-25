import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from alembic.config import Config
from fastapi.responses import JSONResponse

from alembic import command
from fastapi import FastAPI, Request, status
from src.application.ports.errors import UpstreamServiceError
from src.application.services.notification_service import NotificationService
from src.application.usecases.handle_shipment_event import HandleShipmentEventUseCase
from src.domain.events import SHIPMENT_EVENTS_TOPIC
from src.infrastructure.http.catalog import HttpCatalogClient
from src.infrastructure.http.notifications import HttpNotificationsClient
from src.infrastructure.http.payments import HttpPaymentsClient
from src.infrastructure.messaging.kafka_consumer import KafkaShipmentConsumer
from src.infrastructure.messaging.kafka_producer import KafkaEventPublisher
from src.infrastructure.messaging.outbox_relay import OutboxRelay
from src.infrastructure.persistence.database import (
    create_engine,
    create_session_factory,
)
from src.infrastructure.persistence.uow import UnitOfWork
from src.presentation.api.routes import orders
from src.settings import Settings

logger = logging.getLogger(__name__)


def _run_migrations(database_url: str) -> None:
    """Применить Alembic-миграции к БД перед стартом приложения.

    Вызывается в lifespan. Идемпотентно: если схема уже на head —
    no-op. Если есть незакоммиченные миграции — применяет.
    """
    alembic_cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_cfg, "head")


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
        engine = create_engine(settings.database_url)
        await asyncio.to_thread(_run_migrations, settings.database_url)

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

        publisher = KafkaEventPublisher(settings.kafka_bootstrap_servers)
        await publisher.start()
        app.state.publisher = publisher

        relay = OutboxRelay(
            uow_factory=app.state.uow_factory,
            publisher=publisher,
            poll_interval=settings.outbox_poll_interval_seconds,
            batch_size=settings.outbox_batch_size,
        )
        await relay.start()

        shipment_handler = HandleShipmentEventUseCase(
            app.state.uow_factory, NotificationService(app.state.notifications_client)
        )
        consumer = KafkaShipmentConsumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_consumer_group,
            topic=SHIPMENT_EVENTS_TOPIC,
            handler=shipment_handler,
        )
        await consumer.start()

        try:
            yield
        finally:
            await consumer.stop()
            await relay.stop()
            await publisher.stop()
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
