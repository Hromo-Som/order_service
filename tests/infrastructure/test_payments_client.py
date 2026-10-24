import json
from decimal import Decimal

import httpx

from src.infrastructure.http.payments import HttpPaymentsClient


async def test_create_payment_posts_correct_payload():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key"] = request.headers.get("x-api-key")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": "p1",
                "order_id": "o1",
                "amount": "200.00",
                "status": "pending",
                "idempotency_key": "o1:payment",
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = HttpPaymentsClient("http://pay.test/", "secret", http_client)

    async with http_client:
        payment = await client.create_payment(
            order_id="o1",
            amount=Decimal("200.00"),
            callback_url="http://order-service.ns.svc:8000/api/orders/payment-callback",
            idempotency_key="o1:payment",
        )

    assert captured["url"] == "http://pay.test/api/payments"
    assert captured["api_key"] == "secret"
    assert captured["body"]["amount"] == "200.00"
    assert captured["body"]["callback_url"].startswith("http://order-service")
    assert payment.id == "p1"
    assert payment.status == "pending"
