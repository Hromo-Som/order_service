import logging
from decimal import Decimal

import httpx

from src.application.ports.payments import PaymentDTO, PaymentsClient

logger = logging.getLogger(__name__)


class HttpPaymentsClient(PaymentsClient):
    def __init__(self, base_url: str, api_key: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client

    async def create_payment(
        self, order_id: str, amount: Decimal, callback_url: str, idempotency_key: str
    ) -> PaymentDTO:
        payload = {
            "order_id": order_id,
            "amount": str(amount),
            "callback_url": callback_url,
            "idempotency_key": idempotency_key,
        }
        logger.info(
            "Creating payment: order_id=%s amount=%s callback=%s",
            order_id,
            payload["amount"],
            callback_url,
        )

        resp = await self._client.post(
            f"{self._base_url}/api/payments",
            headers={"X-API-Key": self._api_key},
            json=payload,
        )

        if resp.status_code >= httpx.codes.BAD_REQUEST:
            logger.error(
                "Payments create failed: %s %s",
                resp.status_code,
                resp.text[:500],
            )

        resp.raise_for_status()

        data = resp.json()
        return PaymentDTO(
            id=data["id"],
            order_id=data["order_id"],
            amount=data["amount"],
            status=data["status"],
            idempotency_key=data["idempotency_key"],
        )
