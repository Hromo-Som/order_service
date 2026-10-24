import asyncio
import logging

from src.application.ports.outbox import EventPublisher
from src.application.ports.uow import UnitOfWorkFactory

logger = logging.getLogger(__name__)


class OutboxRelay:
    """Периодически публикует неопубликованные outbox-события."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        publisher: EventPublisher,
        poll_interval: float,
        batch_size: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Запустить фоновый цикл публикации."""
        self._task = asyncio.create_task(self._run())
        logger.info(
            "Outbox relay запущен (interval=%.1fs, batch=%d)",
            self._poll_interval,
            self._batch_size,
        )

    async def stop(self) -> None:
        """Остановить цикл. Незакоммиченные события останутся
        в outbox и будут обработаны после рестарта."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("Outbox relay остановлен")

    async def _run(self) -> None:
        """Основной цикл: tick → sleep. Ошибки tick'а не роняют цикл."""
        backoff = self._poll_interval
        while True:
            try:
                await self._tick()
                backoff = self._poll_interval
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Outbox relay tick failed (retrying in %.1fs)", backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue
            await asyncio.sleep(self._poll_interval)

    async def _tick(self) -> None:
        """Одна итерация: забрать пачку, опубликовать, пометить, commit."""
        async with self._uow_factory() as uow:
            events = await uow.outbox.fetch_batch(self._batch_size)
            for event in events:
                try:
                    await self._publisher.publish(
                        topic=event.topic,
                        key=event.key,
                        payload=event.payload,
                    )
                    await uow.outbox.mark_published(event.id)
                except Exception:
                    logger.exception(
                        "Ошибка публикации outbox event %s (topic=%s)",
                        event.id,
                        event.topic,
                    )
            await uow.commit()
            if events:
                logger.info("Outbox relay опубликовал %d event(s)", len(events))
