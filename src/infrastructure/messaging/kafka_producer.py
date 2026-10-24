import json
import logging

from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)


class KafkaEventPublisher:
    """Реализация EventPublisher поверх aiokafka."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        """Создать producer и подключиться к брокерам."""
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            acks="all",
            enable_idempotence=True,
        )
        await self._producer.start()
        logger.info("Kafka producer запущен: %s", self._bootstrap_servers)

    async def stop(self) -> None:
        """Flush буфера и закрыть соединения с брокерами."""
        if self._producer is not None:
            await self._producer.stop()
            logger.info("Kafka producer остановлен")

    async def publish(self, topic: str, key: str, payload: dict) -> None:
        """Опубликовать сообщение с подтверждением от Kafka."""
        if self._producer is None:
            raise RuntimeError("Kafka producer не запущен: start() не вызван")
        await self._producer.send_and_wait(
            topic=topic,
            key=key.encode("utf-8"),
            value=json.dumps(payload).encode("utf-8"),
        )
