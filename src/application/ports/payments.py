from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

PaymentStatus = Literal["pending", "succeeded", "failed"]


@dataclass(frozen=True)
class PaymentDTO:
    """Платёж, созданный Payments Service."""

    id: str
    order_id: str
    amount: str
    status: PaymentStatus
    idempotency_key: str


class PaymentsClient(ABC):
    """Порт доступа к Payments Service."""

    @abstractmethod
    async def create_payment(
        self,
        order_id: str,
        amount: Decimal,
        callback_url: str,
        idempotency_key: str,
    ) -> PaymentDTO:
        """Создать платёж. Бросает UpstreamServiceError при ошибке внешнего сервиса."""
