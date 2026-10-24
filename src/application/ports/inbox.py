from abc import ABC, abstractmethod


class ProcessedEventsRepository(ABC):
    """Inbox-репозиторий для дедупликации входящих событий."""

    @abstractmethod
    async def try_mark_processed(self, dedup_key: str) -> bool:
        """Атомарно зарегистрировать событие как обработанное."""
