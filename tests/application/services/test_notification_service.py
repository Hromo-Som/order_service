from uuid import uuid4

import pytest

from src.application.services.notification_service import NotificationService
from tests.conftest import FakeNotificationsClient


async def test_notify_new():
    client = FakeNotificationsClient()
    service = NotificationService(client)
    order_id = uuid4()

    await service.notify_new(order_id)

    assert len(client.sent) == 1
    n = client.sent[0]
    assert n["message"] == "Ваш заказ создан и ожидает оплаты"
    assert n["reference_id"] == str(order_id)
    assert n["idempotency_key"] == f"order:{order_id}:NEW"


async def test_notify_paid():
    client = FakeNotificationsClient()
    service = NotificationService(client)
    order_id = uuid4()

    await service.notify_paid(order_id)

    assert client.sent[0]["message"] == "Ваш заказ успешно оплачен и готов к отправке"
    assert client.sent[0]["idempotency_key"] == f"order:{order_id}:PAID"


async def test_notify_shipped():
    client = FakeNotificationsClient()
    service = NotificationService(client)
    order_id = uuid4()

    await service.notify_shipped(order_id)

    assert client.sent[0]["message"] == "Ваш заказ отправлен в доставку"
    assert client.sent[0]["idempotency_key"] == f"order:{order_id}:SHIPPED"


async def test_notify_cancelled_includes_reason():
    client = FakeNotificationsClient()
    service = NotificationService(client)
    order_id = uuid4()

    await service.notify_cancelled(order_id, reason="Card declined")

    assert client.sent[0]["message"] == ("Ваш заказ отменен. Причина: Card declined")
    assert client.sent[0]["idempotency_key"] == f"order:{order_id}:CANCELLED"


async def test_idempotency_keys_differ_per_status():
    """Разные статусы одного заказа — разные idempotency_key."""
    client = FakeNotificationsClient()
    service = NotificationService(client)
    order_id = uuid4()

    await service.notify_new(order_id)
    await service.notify_paid(order_id)
    await service.notify_shipped(order_id)
    await service.notify_cancelled(order_id, reason="test")

    keys = [n["idempotency_key"] for n in client.sent]
    assert keys == [
        f"order:{order_id}:NEW",
        f"order:{order_id}:PAID",
        f"order:{order_id}:SHIPPED",
        f"order:{order_id}:CANCELLED",
    ]
    assert len(set(keys)) == 4


async def test_same_status_same_key_is_deterministic():
    """Повторный вызов notify_paid → тот же ключ."""
    client = FakeNotificationsClient()
    service = NotificationService(client)
    order_id = uuid4()

    await service.notify_paid(order_id)
    await service.notify_paid(order_id)

    assert len(client.sent) == 2
    assert client.sent[0]["idempotency_key"] == client.sent[1]["idempotency_key"]


@pytest.mark.parametrize("method_name", ["notify_new", "notify_paid", "notify_shipped"])
async def test_send_safe_swallows_errors(method_name):
    """Сбой Notifications не пробрасывается — требование ТЗ шага 4."""
    client = FakeNotificationsClient()
    client.fail_next = True
    service = NotificationService(client)

    await getattr(service, method_name)(uuid4())

    assert client.sent == []


async def test_send_safe_swallows_errors_cancelled():
    client = FakeNotificationsClient()
    client.fail_next = True
    service = NotificationService(client)

    await service.notify_cancelled(uuid4(), reason="test")

    assert client.sent == []
