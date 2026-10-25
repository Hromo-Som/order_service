import asyncio
import logging
import signal

import httpx

from src.application.services.notification_service import NotificationService
from src.application.usecases.handle_shipment_event import HandleShipmentEventUseCase
from src.domain.events import SHIPMENT_EVENTS_TOPIC
from src.infrastructure.http.notifications import HttpNotificationsClient
from src.infrastructure.messaging.kafka_consumer import KafkaShipmentConsumer
from src.infrastructure.messaging.kafka_producer import KafkaEventPublisher
from src.infrastructure.messaging.outbox_relay import OutboxRelay
from src.infrastructure.persistence.database import (
    create_engine,
    create_session_factory,
)
from src.infrastructure.persistence.uow import UnitOfWork
from src.settings import Settings

logger = logging.getLogger(__name__)


async def run_worker() -> None:
    """Запустить worker: relay + consumer до SIGTERM/SIGINT."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )

    settings = Settings()

    logging.getLogger().setLevel(settings.log_level.upper())

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    uow_factory = UnitOfWork(session_factory)

    publisher = KafkaEventPublisher(settings.kafka_bootstrap_servers)
    await publisher.start()

    relay = OutboxRelay(
        uow_factory=uow_factory,
        publisher=publisher,
        poll_interval=settings.outbox_poll_interval_seconds,
        batch_size=settings.outbox_batch_size,
    )
    await relay.start()

    http_client = httpx.AsyncClient(timeout=10.0)
    notifications_client = HttpNotificationsClient(
        base_url=settings.capashino_base_url,
        api_key=settings.capashino_api_token.get_secret_value(),
        client=http_client,
    )
    notification_service = NotificationService(notifications_client)
    shipment_handler = HandleShipmentEventUseCase(uow_factory, notification_service)

    consumer = KafkaShipmentConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        topic=SHIPMENT_EVENTS_TOPIC,
        handler=shipment_handler,
    )
    await consumer.start()

    logger.info("Worker запущен (relay + consumer)")

    stop_event = asyncio.Event()

    def _on_signal(sig: signal.Signals) -> None:
        logger.info("Получен %s, остановка worker...", sig.name)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _on_signal, sig)

    try:
        await stop_event.wait()
    finally:
        await consumer.stop()
        await relay.stop()
        await publisher.stop()
        await http_client.aclose()
        await engine.dispose()
        logger.info("Worker остановлен")
