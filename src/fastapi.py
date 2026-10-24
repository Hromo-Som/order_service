import logging
from contextlib import asynccontextmanager

import httpx
from fastapi.responses import JSONResponse

from fastapi import FastAPI, Request, status
from src.application.usecases.handle_shipment_event import HandleShipmentEventUseCase
from src.domain.events import SHIPMENT_EVENTS_TOPIC
from src.infrastructure.http.catalog import HttpCatalogClient
from src.infrastructure.http.payments import HttpPaymentsClient
from src.infrastructure.messaging.kafka_consumer import KafkaShipmentConsumer
from src.infrastructure.messaging.kafka_producer import KafkaEventPublisher
from src.infrastructure.messaging.outbox_relay import OutboxRelay
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
    """Фабрика FastAPI-приложения — composition root."""
    settings = Settings()

    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True, 
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Управление ресурсами приложения: startup и graceful shutdown."""
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

        shipment_handler = HandleShipmentEventUseCase(app.state.uow_factory)
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

    @app.exception_handler(httpx.HTTPStatusError)
    async def _httpx_status(
        request: Request, exc: httpx.HTTPStatusError
    ) -> JSONResponse:
        """Upstream вернул 4xx/5xx → 502 клиенту."""
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
        """Upstream недоступен (сеть, таймаут, DNS) → 502 клиенту."""
        logger.error(
            "Upstream unreachable: %s", exc.request.url if exc.request else "?"
        )
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": "Внешний сервис недоступен"},
        )

    @app.get("/healthz", tags=["health"])
    async def healthz():
        """Liveness/readiness probe."""
        return {"status": "ok"}

    return app
