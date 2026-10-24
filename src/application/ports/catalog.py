from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogItem:
    """Товар из Catalog Service."""

    id: str
    name: str
    price: str
    available_qty: int


class CatalogClient(ABC):
    """Порт доступа к Catalog Service."""

    @abstractmethod
    async def get_item(self, item_id: str) -> CatalogItem:
        """Получить товар по идентификатору. Бросает ItemNotFoundError, если товара нет в каталоге."""
