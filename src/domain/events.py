from dataclasses import dataclass
from typing import Any
from uuid import UUID

ORDER_EVENTS_TOPIC = "student_system-order.events"
SHIPMENT_EVENTS_TOPIC = "student_system-shipment.events"


@dataclass(frozen=True)
class OrderPaidEvent:
    """Событие order.paid → student_system-order.events."""

    order_id: UUID
    item_id: str
    quantity: int
    idempotency_key: UUID

    @property
    def event_type(self) -> str:
        """Тип события — всегда "order.paid"."""
        return "order.paid"

    def to_payload(self) -> dict[str, Any]:
        """Сериализовать в wire-формат для Kafka."""
        return {
            "event_type": self.event_type,
            "order_id": str(self.order_id),
            "item_id": self.item_id,
            "quantity": self.quantity,
            "idempotency_key": str(self.idempotency_key),
        }


@dataclass(frozen=True)
class ShipmentEvent:
    """Событие order.shipped / order.cancelled ← student_system-shipment.events."""

    event_type: str
    order_id: UUID
    item_id: str
    quantity: int
    shipment_id: str | None = None
    reason: str | None = None

    @property
    def dedup_key(self) -> str:
        """Ключ идемпотентности для inbox."""
        return f"{self.event_type}:{self.order_id}"
