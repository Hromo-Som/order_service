from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogItem:
    id: str
    name: str
    price: str
    available_qty: int


class CatalogClient(ABC):
    @abstractmethod
    async def get_item(self, item_id: str) -> CatalogItem:
        """Бросает ItemNotFoundError, если товара нет в каталоге."""
