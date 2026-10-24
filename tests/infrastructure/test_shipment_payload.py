from uuid import UUID

import pytest
from pydantic import ValidationError

from src.infrastructure.messaging.schemas import ShipmentEventPayload


def test_valid_shipped_payload():
    payload = ShipmentEventPayload.model_validate_json(
        '{"event_type":"order.shipped","order_id":"550e8400-e29b-41d4-a716-446655440000",'
        '"item_id":"i1","quantity":2,"shipment_id":"ship-1"}'
    )
    assert isinstance(payload.order_id, UUID)
    assert payload.event_type == "order.shipped"
    assert payload.shipment_id == "ship-1"


def test_valid_cancelled_payload():
    payload = ShipmentEventPayload.model_validate_json(
        '{"event_type":"order.cancelled","order_id":"550e8400-e29b-41d4-a716-446655440000",'
        '"item_id":"i1","quantity":2,"reason":"Insufficient stock"}'
    )
    assert payload.event_type == "order.cancelled"
    assert payload.reason == "Insufficient stock"


def test_rejects_invalid_uuid():
    with pytest.raises(ValidationError):
        ShipmentEventPayload.model_validate_json(
            '{"event_type":"order.shipped","order_id":"not-a-uuid",'
            '"item_id":"i1","quantity":1}'
        )


def test_rejects_unknown_event_type():
    """Только order.shipped и order.cancelled — иначе consumer упадёт
    на else-ветке, заблокировав offset. Парсер должен отсечь заранее.
    """
    with pytest.raises(ValidationError):
        ShipmentEventPayload.model_validate_json(
            '{"event_type":"order.refunded","order_id":"550e8400-e29b-41d4-a716-446655440000",'
            '"item_id":"i1","quantity":1}'
        )


def test_rejects_missing_required_field():
    with pytest.raises(ValidationError):
        ShipmentEventPayload.model_validate_json(
            '{"event_type":"order.shipped","order_id":"550e8400-e29b-41d4-a716-446655440000"}'
        )
