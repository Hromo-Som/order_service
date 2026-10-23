import pytest
from pydantic import ValidationError

from src.domain.entities import Order
from src.domain.enums import OrderStatusEnum
from src.domain.exceptions import InvalidOrderTransitionError


def test_create_sets_new_status_and_timestamps():
    order = Order.create("u1", "item-1", 2, "key-1")

    assert order.status == OrderStatusEnum.NEW
    assert order.user_id == "u1"
    assert order.item_id == "item-1"
    assert order.quantity == 2
    assert order.idempotency_key == "key-1"
    assert order.created_at == order.updated_at


def test_create_generates_unique_ids():
    o1 = Order.create("u1", "item-1", 1, "k1")
    o2 = Order.create("u1", "item-1", 1, "k2")
    assert o1.id != o2.id


def test_create_rejects_non_positive_quantity():
    with pytest.raises(ValidationError) as exc:
        Order.create("u1", "item-1", 0, "k1")

    errors = exc.value.errors()
    assert any(e["loc"] == ("quantity",) for e in errors)

def test_pay_from_new():
    order = Order.create("u1", "item-1", 1, "k1")
    prev_updated = order.updated_at
    order.pay()

    assert order.status == OrderStatusEnum.PAID
    assert order.updated_at >= prev_updated


def test_pay_fails_from_paid():
    order = Order.create("u1", "item-1", 1, "k1")
    order.pay()
    with pytest.raises(InvalidOrderTransitionError):
        order.pay()


def test_pay_fails_from_cancelled():
    order = Order.create("u1", "item-1", 1, "k1")
    order.cancel()
    with pytest.raises(InvalidOrderTransitionError):
        order.pay()


def test_ship_from_paid():
    order = Order.create("u1", "item-1", 1, "k1")
    order.pay()
    order.ship()
    assert order.status == OrderStatusEnum.SHIPPED


def test_ship_fails_from_new():
    order = Order.create("u1", "item-1", 1, "k1")
    with pytest.raises(InvalidOrderTransitionError):
        order.ship()


def test_cancel_from_new():
    order = Order.create("u1", "item-1", 1, "k1")
    order.cancel()
    assert order.status == OrderStatusEnum.CANCELLED


def test_cancel_from_paid():
    order = Order.create("u1", "item-1", 1, "k1")
    order.pay()
    order.cancel()
    assert order.status == OrderStatusEnum.CANCELLED


def test_cancel_fails_from_shipped():
    order = Order.create("u1", "item-1", 1, "k1")
    order.pay()
    order.ship()
    with pytest.raises(InvalidOrderTransitionError):
        order.cancel()


def test_cancel_fails_from_cancelled():
    order = Order.create("u1", "item-1", 1, "k1")
    order.cancel()
    with pytest.raises(InvalidOrderTransitionError):
        order.cancel()
