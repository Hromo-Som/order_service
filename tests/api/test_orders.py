async def test_healthz(api_client):
    response = await api_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_create_order_201(api_client):
    response = await api_client.post(
        "/api/orders",
        json={
            "user_id": "u1",
            "item_id": "item-1",
            "quantity": 2,
            "idempotency_key": "k1",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == "u1"
    assert body["item_id"] == "item-1"
    assert body["quantity"] == 2
    assert body["status"] == "NEW"
    assert "id" in body
    assert body["created_at"] == body["updated_at"]


async def test_create_order_idempotent(api_client):
    payload = {
        "user_id": "u1",
        "item_id": "item-1",
        "quantity": 1,
        "idempotency_key": "k1",
    }

    r1 = await api_client.post("/api/orders", json=payload)
    r2 = await api_client.post("/api/orders", json=payload)

    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


async def test_create_order_insufficient_stock_400(api_client):
    response = await api_client.post(
        "/api/orders",
        json={
            "user_id": "u1",
            "item_id": "item-1",
            "quantity": 999,
            "idempotency_key": "k1",
        },
    )

    assert response.status_code == 400
    assert "Недопустимое количество" in response.json()["detail"]


async def test_create_order_item_not_found_400(api_client):
    response = await api_client.post(
        "/api/orders",
        json={
            "user_id": "u1",
            "item_id": "missing",
            "quantity": 1,
            "idempotency_key": "k1",
        },
    )

    assert response.status_code == 400
    assert "не найден" in response.json()["detail"]


async def test_create_order_validation_422(api_client):
    response = await api_client.post(
        "/api/orders",
        json={"user_id": "", "item_id": "", "quantity": 0, "idempotency_key": ""},
    )

    assert response.status_code == 422


async def test_get_order_200(api_client):
    created = await api_client.post(
        "/api/orders",
        json={
            "user_id": "u1",
            "item_id": "item-1",
            "quantity": 1,
            "idempotency_key": "k1",
        },
    )
    order_id = created.json()["id"]

    response = await api_client.get(f"/api/orders/{order_id}")

    assert response.status_code == 200
    assert response.json()["id"] == order_id


async def test_get_order_404(api_client):
    response = await api_client.get(
        "/api/orders/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404
    assert "не найден" in response.json()["detail"]


async def test_get_order_invalid_uuid_422(api_client):
    response = await api_client.get("/api/orders/not-a-uuid")
    assert response.status_code == 422
