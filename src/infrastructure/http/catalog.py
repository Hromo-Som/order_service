import logging

import httpx

from src.application.ports.catalog import CatalogClient, CatalogItem
from src.application.ports.errors import UpstreamServiceError
from src.domain.exceptions import ItemNotFoundError

logger = logging.getLogger(__name__)


class HttpCatalogClient(CatalogClient):
    """HTTP-адаптер Catalog Service (Capashino API)."""

    def __init__(self, base_url: str, api_key: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client

    async def get_item(self, item_id: str) -> CatalogItem:
        """Получить товар по идентификатору."""
        try:
            resp = await self._client.get(
                f"{self._base_url}/api/catalog/items/{item_id}",
                headers={"X-API-Key": self._api_key},
            )
        except httpx.RequestError as e:
            logger.exception("Catalog недоступен: item_id=%s", item_id)
            raise UpstreamServiceError("catalog", f"transport: {e}") from e

        if resp.status_code in (
            httpx.codes.NOT_FOUND,
            httpx.codes.UNPROCESSABLE_ENTITY,
        ):
            raise ItemNotFoundError(item_id)

        if resp.status_code >= httpx.codes.BAD_REQUEST:
            logger.error("Catalog error: %s %s", resp.status_code, resp.text[:500])
            raise UpstreamServiceError(
                "catalog", f"HTTP {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        return CatalogItem(
            id=data["id"],
            name=data["name"],
            price=data["price"],
            available_qty=data["available_qty"],
        )
