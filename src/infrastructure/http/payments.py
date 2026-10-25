import logging
from decimal import Decimal

import httpx

from src.application.ports.errors import UpstreamServiceError
from src.application.ports.payments import PaymentDTO, PaymentsClient

logger = logging.getLogger(__name__)


class HttpPaymentsClient(PaymentsClient):
    """HTTP-адаптер Payments Service (Capashino API)."""

    def __init__(self, base_url: str, api_key: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client

    async def create_payment(
        self, order_id: str, amount: Decimal, callback_url: str, idempotency_key: str
    ) -> PaymentDTO:
        """Создать платёж."""
        payload = {
            "order_id": order_id,
            "amount": str(amount),
            "callback_url": callback_url,
            "idempotency_key": idempotency_key,
        }
        logger.info(
            "Создание payment: order_id=%s amount=%s callback=%s",
            order_id,
            payload["amount"],
            callback_url,
        )

        try:
            resp = await self._client.post(
                f"{self._base_url}/api/payments",
                headers={"X-API-Key": self._api_key},
                json=payload,
            )
        except httpx.RequestError as e:
            logger.exception("Payments недоступен: order_id=%s", order_id)
            raise UpstreamServiceError("payments", f"transport: {e}") from e

        if resp.status_code >= httpx.codes.BAD_REQUEST:
            logger.error(
                "Payments create failed: %s %s",
                resp.status_code,
                resp.text[:500],
            )
            raise UpstreamServiceError(
                "payments", f"HTTP {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        return PaymentDTO(
            id=data["id"],
            order_id=data["order_id"],
            amount=data["amount"],
            status=data["status"],
            idempotency_key=data["idempotency_key"],
        )
