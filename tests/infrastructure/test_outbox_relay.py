from uuid import uuid4

from src.infrastructure.messaging.outbox_relay import OutboxRelay


async def _add_event(uow_factory, event_type="order.paid", key=None):
    """Хелпер: положить событие в outbox (как это сделал бы use case)."""
    async with uow_factory() as uow:
        await uow.outbox.add(
            topic="test.topic",
            event_type=event_type,
            key=key or str(uuid4()),
            payload={"event_type": event_type, "foo": "bar"},
            idempotency_key=f"idem-{event_type}",
        )
        await uow.commit()


def _make_relay(uow_factory, publisher, batch_size=10) -> OutboxRelay:
    return OutboxRelay(
        uow_factory=uow_factory,
        publisher=publisher,
        poll_interval=0.01,
        batch_size=batch_size,
    )


async def test_tick_publishes_and_marks(uow_factory, publisher, outbox):
    """Один tick: publish + mark_published для всех событий пачки."""
    await _add_event(uow_factory)
    await _add_event(uow_factory)

    relay = _make_relay(uow_factory, publisher)
    await relay._tick()

    assert len(publisher.published) == 2
    assert all(p["topic"] == "test.topic" for p in publisher.published)
    assert outbox.unpublished() == []


async def test_tick_empty_outbox_noop(uow_factory, publisher, outbox):
    relay = _make_relay(uow_factory, publisher)
    await relay._tick()

    assert publisher.published == []
    assert outbox.all() == []


async def test_tick_on_publish_failure_does_not_mark(uow_factory, publisher, outbox):
    """Ошибка Kafka → событие НЕ помечено, следующий tick попробует снова."""
    await _add_event(uow_factory)
    publisher.fail_next = True

    relay = _make_relay(uow_factory, publisher)
    await relay._tick()

    assert publisher.published == []
    assert len(outbox.unpublished()) == 1


async def test_tick_retries_after_failure(uow_factory, publisher, outbox):
    """После устранения ошибки следующий tick публикует и помечает."""
    await _add_event(uow_factory)
    publisher.fail_next = True

    relay = _make_relay(uow_factory, publisher)
    await relay._tick()
    await relay._tick()

    assert len(publisher.published) == 1
    assert outbox.unpublished() == []


async def test_tick_respects_batch_size(uow_factory, publisher, outbox):
    """batch_size=2 → за один tick публикуется не больше 2 событий."""
    for _ in range(5):
        await _add_event(uow_factory)

    relay = _make_relay(uow_factory, publisher, batch_size=2)
    await relay._tick()

    assert len(publisher.published) == 2
    assert len(outbox.unpublished()) == 3


async def test_tick_multiple_batches_drain_outbox(uow_factory, publisher, outbox):
    """Последовательные tick'и разгребают outbox полностью."""
    for _ in range(5):
        await _add_event(uow_factory)

    relay = _make_relay(uow_factory, publisher, batch_size=2)
    for _ in range(3):
        await relay._tick()

    assert len(publisher.published) == 5
    assert outbox.unpublished() == []


async def test_payload_preserved_through_relay(uow_factory, publisher):
    """Payload, topic, key — передаются в publisher без изменений."""
    async with uow_factory() as uow:
        await uow.outbox.add(
            topic="custom.topic",
            event_type="custom.event",
            key="partition-key",
            payload={"nested": {"a": 1}, "list": [1, 2, 3]},
            idempotency_key="idem-1",
        )
        await uow.commit()

    await _make_relay(uow_factory, publisher)._tick()

    assert len(publisher.published) == 1
    p = publisher.published[0]
    assert p["topic"] == "custom.topic"
    assert p["key"] == "partition-key"
    assert p["payload"] == {"nested": {"a": 1}, "list": [1, 2, 3]}
