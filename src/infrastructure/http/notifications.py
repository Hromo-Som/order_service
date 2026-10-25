import logging

import httpx

from src.application.ports.errors import UpstreamServiceError
from src.application.ports.notifications import NotificationDTO, NotificationsClient

logger = logging.getLogger(__name__)


class HttpNotificationsClient(NotificationsClient):
    """HTTP-адаптер Notifications Service (Capashino API)."""

    def __init__(self, base_url: str, api_key: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client

    async def send(
        self, message: str, reference_id: str, idempotency_key: str
    ) -> NotificationDTO:
        """POST /api/notifications с X-API-Key."""
        payload = {
            "message": message,
            "reference_id": reference_id,
            "idempotency_key": idempotency_key,
        }

        logger.info(
            "Отправка уведомления: reference_id=%s key=%s",
            reference_id,
            idempotency_key,
        )

        try:
            resp = await self._client.post(
                url=f"{self._base_url}/api/notifications",
                headers={"X-API-Key": self._api_key},
                json=payload,
            )
        except httpx.RequestError as e:
            raise UpstreamServiceError("notifications", f"transport: {e}") from e

        if resp.status_code >= httpx.codes.BAD_REQUEST:
            logger.error(
                "Ошибка отправки уведомления: %s %s", resp.status_code, resp.text[:500]
            )
            raise UpstreamServiceError(
                "notifications", f"HTTP {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()

        return NotificationDTO(
            id=data["id"],
            reference_id=data["reference_id"],
            message=data["message"],
            created_at=data["created_at"],
        )
