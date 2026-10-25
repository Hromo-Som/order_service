import json

import httpx
import pytest

from src.infrastructure.http.notifications import HttpNotificationsClient


def _make_client(handler) -> tuple[HttpNotificationsClient, httpx.AsyncClient]:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = HttpNotificationsClient("http://notif.test", "secret", http_client)
    return client, http_client


async def test_send_posts_correct_payload():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["api_key"] = request.headers.get("x-api-key")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": "n1",
                "reference_id": "o1",
                "message": "hello",
                "created_at": "2026-01-01T00:00:00Z",
            },
        )

    client, http_client = _make_client(handler)
    async with http_client:
        result = await client.send("hello", "o1", "order:o1:NEW")

    assert captured["url"] == "http://notif.test/api/notifications"
    assert captured["method"] == "POST"
    assert captured["api_key"] == "secret"
    assert captured["body"] == {
        "message": "hello",
        "reference_id": "o1",
        "idempotency_key": "order:o1:NEW",
    }
    assert result.id == "n1"
    assert result.reference_id == "o1"


async def test_send_raises_on_4xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "invalid"})

    client, http_client = _make_client(handler)
    async with http_client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.send("hello", "o1", "key")


async def test_send_raises_on_5xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client, http_client = _make_client(handler)
    async with http_client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.send("hello", "o1", "key")


async def test_base_url_trailing_slash_stripped():
    """base_url с хвостовым слэшем не даёт //api/..."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            201,
            json={
                "id": "n1",
                "reference_id": "o1",
                "message": "x",
                "created_at": "2026-01-01T00:00:00Z",
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = HttpNotificationsClient("http://notif.test/", "secret", http_client)

    async with http_client:
        await client.send("x", "o1", "key")

    assert captured["url"] == "http://notif.test/api/notifications"
