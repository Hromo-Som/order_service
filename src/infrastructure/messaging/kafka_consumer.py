import asyncio
import logging
from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaConsumer
from pydantic import ValidationError

from src.domain.events import ShipmentEvent
from src.infrastructure.messaging.schemas import ShipmentEventPayload

logger = logging.getLogger(__name__)


class KafkaShipmentConsumer:
    """Фоновый consumer student_system-shipment.events."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topic: str,
        handler: Callable[[ShipmentEvent], Awaitable[None]],
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._topic = topic
        self._handler = handler
        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Подключиться к Kafka и запустить фоновую задачу чтения."""
        self._consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self._consumer.start()
        self._task = asyncio.create_task(self._run())
        logger.info(
            "Kafka consumer запущен: topic=%s group=%s",
            self._topic,
            self._group_id,
        )

    async def stop(self) -> None:
        """Остановить задачу и закрыть consumer."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._consumer is not None:
            await self._consumer.stop()
            logger.info("Kafka consumer остановлен")

    async def _run(self) -> None:
        """Основной цикл: poll → parse → handle → commit."""
        if self._consumer is None:
            raise RuntimeError("Kafka consumer не запущен: start() не вызван")
        async for msg in self._consumer:
            if msg.value is None:
                logger.warning(
                    "Пустое значение события в партиции=%s offset=%s — skipping",
                    msg.partition,
                    msg.offset,
                )
                await self._consumer.commit()
                continue
            try:
                raw = ShipmentEventPayload.model_validate_json(msg.value)
                event = ShipmentEvent(
                    event_type=raw.event_type,
                    order_id=raw.order_id,
                    item_id=raw.item_id,
                    quantity=raw.quantity,
                    shipment_id=raw.shipment_id,
                    reason=raw.reason,
                )
                await self._handler(event)
                await self._consumer.commit()
                logger.info(
                    "Обработано событие %s для заказа %s (partition=%s offset=%s)",
                    event.event_type,
                    event.order_id,
                    msg.partition,
                    msg.offset,
                )
            except ValidationError:
                logger.exception(
                    "Невалидный shipment event в партиции=%s offset=%s",
                    msg.partition,
                    msg.offset,
                )
                await self._consumer.commit()
                continue
            except Exception:
                logger.exception(
                    "Ошибка обработки события в партиции=%s offset=%s",
                    msg.partition,
                    msg.offset,
                )
