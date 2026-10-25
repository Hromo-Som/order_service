from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationDTO:
    """Уведомление, отправленное Notifications Service."""

    id: str
    reference_id: str
    message: str
    created_at: str


class NotificationsClient(ABC):
    """Порт доступа к Notifications Service.
    Реализация — HttpNotificationsClient поверх Capashino API."""

    @abstractmethod
    async def send(
        self,
        message: str,
        reference_id: str,
        idempotency_key: str,
    ) -> NotificationDTO:
        """Отправить уведомление."""
