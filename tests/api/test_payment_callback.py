async def _create_order(api_client) -> str:
    """Хелпер: создать заказ в статусе NEW через API, вернуть id."""
    resp = await api_client.post(
        "/api/orders",
        json={
            "user_id": "u1",
            "item_id": "item-1",
            "quantity": 1,
            "idempotency_key": "k1",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_payment_callback_success(api_client):
    """succeeded переводит NEW → PAID."""
    order_id = await _create_order(api_client)

    resp = await api_client.post(
        "/api/orders/payment-callback",
        json={
            "payment_id": "p1",
            "order_id": order_id,
            "status": "succeeded",
            "amount": "100.00",
            "error_message": None,
        },
    )

    assert resp.status_code == 200
    get_resp = await api_client.get(f"/api/orders/{order_id}")
    assert get_resp.json()["status"] == "PAID"


async def test_payment_callback_failure(api_client):
    """failed переводит NEW → CANCELLED."""
    order_id = await _create_order(api_client)

    resp = await api_client.post(
        "/api/orders/payment-callback",
        json={
            "payment_id": "p1",
            "order_id": order_id,
            "status": "failed",
            "amount": "100.00",
            "error_message": "Card declined",
        },
    )

    assert resp.status_code == 200
    get_resp = await api_client.get(f"/api/orders/{order_id}")
    assert get_resp.json()["status"] == "CANCELLED"


async def test_payment_callback_idempotent(api_client):
    """Повторный succeeded — 200 и тот же статус PAID (no-op)."""
    order_id = await _create_order(api_client)
    payload = {
        "payment_id": "p1",
        "order_id": order_id,
        "status": "succeeded",
        "amount": "100.00",
    }

    r1 = await api_client.post("/api/orders/payment-callback", json=payload)
    r2 = await api_client.post("/api/orders/payment-callback", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    get_resp = await api_client.get(f"/api/orders/{order_id}")
    assert get_resp.json()["status"] == "PAID"


async def test_payment_callback_unknown_order_returns_200(api_client):
    """Неизвестный заказ — 200, а не 404."""
    resp = await api_client.post(
        "/api/orders/payment-callback",
        json={
            "payment_id": "p1",
            "order_id": "00000000-0000-0000-0000-000000000000",
            "status": "succeeded",
            "amount": "100.00",
        },
    )
    assert resp.status_code == 200


async def test_payment_callback_invalid_uuid_422(api_client):
    """Невалидный UUID в order_id — 422 от Pydantic, до use case."""
    resp = await api_client.post(
        "/api/orders/payment-callback",
        json={
            "payment_id": "p1",
            "order_id": "not-a-uuid",
            "status": "succeeded",
            "amount": "100.00",
        },
    )
    assert resp.status_code == 422


async def test_create_order_returns_502_on_payment_failure(api_client, payments):
    """Payments недоступен → 502 клиенту (не 500)."""
    payments.set_fail(True)
    resp = await api_client.post(
        "/api/orders",
        json={
            "user_id": "u1",
            "item_id": "item-1",
            "quantity": 1,
            "idempotency_key": "k1",
        },
    )
    assert resp.status_code == 502
