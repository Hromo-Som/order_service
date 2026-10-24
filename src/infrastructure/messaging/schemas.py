from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ShipmentEventPayload(BaseModel):
    """Wire-формат события от Shipping Service."""

    event_type: str = Field(pattern=r"^order\.(shipped|cancelled)$")
    order_id: UUID
    item_id: str
    quantity: int
    shipment_id: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _check_payload_matches_event(self) -> ShipmentEventPayload:
        """Проверить, что для event_type заполнено нужное поле."""
        if self.event_type == "order.shipped" and not self.shipment_id:
            raise ValueError("order.shipped требует shipment_id")
        if self.event_type == "order.cancelled" and not self.reason:
            raise ValueError("order.cancelled требует reason")
        return self
