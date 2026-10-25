import httpx
import pytest

from src.application.ports.errors import UpstreamServiceError
from src.domain.exceptions import ItemNotFoundError
from src.infrastructure.http.catalog import HttpCatalogClient


def _make_client(handler) -> tuple[HttpCatalogClient, httpx.AsyncClient]:
    """Собрать HttpCatalogClient с MockTransport — без реальной сети."""
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    catalog = HttpCatalogClient(
        base_url="http://catalog.test", api_key="secret-key", client=http_client
    )
    return catalog, http_client


async def test_get_item_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "item-1",
                "name": "Widget",
                "price": "100.00",
                "available_qty": 5,
            },
        )

    catalog, client = _make_client(handler)
    async with client:
        item = await catalog.get_item("item-1")

    assert item.id == "item-1"
    assert item.name == "Widget"
    assert item.available_qty == 5


async def test_get_item_404_raises_item_not_found():
    """404 от Catalog → доменное ItemNotFoundError, не httpx.HTTPStatusError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    catalog, client = _make_client(handler)
    async with client:
        with pytest.raises(ItemNotFoundError):
            await catalog.get_item("missing")


async def test_get_item_sends_api_key_and_correct_url():
    """Проверка контракта запроса: путь, base_url, X-API-Key."""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key"] = request.headers.get("x-api-key", "")
        return httpx.Response(
            200,
            json={"id": "item-1", "name": "W", "price": "1.00", "available_qty": 1},
        )

    catalog, client = _make_client(handler)
    async with client:
        await catalog.get_item("item-1")

    assert captured["url"] == "http://catalog.test/api/catalog/items/item-1"
    assert captured["api_key"] == "secret-key"


async def test_get_item_500_propagates():
    """5xx не мапится в доменную ошибку — летит UpstreamServiceError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    catalog, client = _make_client(handler)
    async with client:
        with pytest.raises(UpstreamServiceError):
            await catalog.get_item("item-1")
