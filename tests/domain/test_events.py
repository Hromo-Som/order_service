from uuid import uuid4

from src.domain.events import OrderPaidEvent, ShipmentEvent


def test_order_paid_event_payload():
    """to_payload — wire-формат для Kafka: UUID в строке, поля как в ТЗ."""
    event = OrderPaidEvent(
        order_id=uuid4(),
        item_id="item-1",
        quantity=10,
        idempotency_key=uuid4(),
    )

    payload = event.to_payload()

    assert payload["event_type"] == "order.paid"
    assert payload["item_id"] == "item-1"
    assert payload["quantity"] == 10
    assert isinstance(payload["order_id"], str)
    assert isinstance(payload["idempotency_key"], str)


def test_order_paid_event_idempotency_key_unique():
    """Два события на один заказ — разные idempotency_key."""
    a = OrderPaidEvent(uuid4(), "i", 1, uuid4())
    b = OrderPaidEvent(uuid4(), "i", 1, uuid4())
    assert a.idempotency_key != b.idempotency_key


def test_shipment_event_dedup_key_shipped():
    order_id = uuid4()
    event = ShipmentEvent(
        event_type="order.shipped",
        order_id=order_id,
        item_id="i1",
        quantity=1,
        shipment_id="s1",
    )
    assert event.dedup_key == f"order.shipped:{order_id}"


def test_shipment_event_dedup_key_cancelled():
    order_id = uuid4()
    event = ShipmentEvent(
        event_type="order.cancelled",
        order_id=order_id,
        item_id="i1",
        quantity=1,
        reason="Insufficient stock",
    )
    assert event.dedup_key == f"order.cancelled:{order_id}"


def test_shipment_event_dedup_key_differs_by_event_type():
    """Один заказ может быть отменён И отгружен (разные event_type) —
    dedup_key должен различать их, иначе inbox заглушит второе событие.
    """
    order_id = uuid4()
    shipped = ShipmentEvent("order.shipped", order_id, "i", 1, shipment_id="s")
    cancelled = ShipmentEvent("order.cancelled", order_id, "i", 1, reason="r")
    assert shipped.dedup_key != cancelled.dedup_key
