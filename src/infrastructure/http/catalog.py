import httpx

from src.application.ports.catalog import CatalogClient, CatalogItem
from src.domain.exceptions import ItemNotFoundError


class HttpCatalogClient(CatalogClient):
    """HTTP-адаптер Catalog Service (Capashino API)."""

    def __init__(self, base_url: str, api_key: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client

    async def get_item(self, item_id: str) -> CatalogItem:
        """Получить товар по идентификатору."""
        resp = await self._client.get(
            f"{self._base_url}/api/catalog/items/{item_id}",
            headers={"X-API-Key": self._api_key},
        )

        if resp.status_code == httpx.codes.NOT_FOUND:
            raise ItemNotFoundError(item_id)
        resp.raise_for_status()

        data = resp.json()
        return CatalogItem(
            id=data["id"],
            name=data["name"],
            price=data["price"],
            available_qty=data["available_qty"],
        )
