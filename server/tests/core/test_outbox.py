"""Tests for the transactional outbox: ``add_event`` / ``EventRegistry`` / ``relay_once``.

The single seam is the public API of ``metis.core.outbox`` against a real
Postgres with migrations applied (``alembic upgrade head``). Tests assert only
what a caller sees: handler calls, ``RelayResult`` counts and the row state.

Set ``TEST_DATABASE_URL`` to point at a migrated database; tests skip when none
is reachable or ``core.outbox`` is missing.
"""

from __future__ import annotations

import asyncio
import os
from collections import Counter
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from structlog.testing import capture_logs

from metis.core.outbox import (
    MAX_ATTEMPTS,
    RELAY_BATCH_SIZE,
    DomainEvent,
    DomainEventType,
    EventRegistry,
    RelayResult,
    add_event,
    relay_once,
)

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/metis"
)
WORKSPACE_ID = uuid4()
HANDLER_DELAY_SECONDS = 0.005
OVER_ONE_BATCH = RELAY_BATCH_SIZE + 50

Sessionmaker = async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def sessionmaker() -> AsyncIterator[Sessionmaker]:
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(text("SELECT to_regclass('core.outbox') IS NOT NULL"))
    except Exception:  # noqa: BLE001
        await engine.dispose()
        pytest.skip("Postgres not reachable")
    if not exists:
        await engine.dispose()
        pytest.skip("core.outbox missing; run `alembic upgrade head`")

    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE core.outbox"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE core.outbox"))
    await engine.dispose()


def _event(payload: dict[str, object] | None = None) -> DomainEvent:
    return DomainEvent(
        workspace_id=WORKSPACE_ID,
        type=DomainEventType.SPEC_CONFIRMED,
        payload=payload or {},
    )


async def _commit_events(sm: Sessionmaker, events: list[DomainEvent]) -> None:
    async with sm() as session, session.begin():
        for event in events:
            add_event(session, event)


async def _row(sm: Sessionmaker, event_id: UUID) -> tuple[object, int]:
    async with sm() as session:
        result = await session.execute(
            text("SELECT published_at, attempts FROM core.outbox WHERE id = :id"),
            {"id": event_id},
        )
        published_at, attempts = result.one()
        return published_at, attempts


def _recording_registry() -> tuple[EventRegistry, list[DomainEvent]]:
    registry = EventRegistry()
    delivered: list[DomainEvent] = []

    @registry.on(DomainEventType.SPEC_CONFIRMED)
    async def record(event: DomainEvent) -> None:
        await asyncio.sleep(HANDLER_DELAY_SECONDS)
        delivered.append(event)

    return registry, delivered


def _failing_registry(fail_ids: set[UUID] | None = None) -> EventRegistry:
    registry = EventRegistry()

    @registry.on(DomainEventType.SPEC_CONFIRMED)
    async def fail(event: DomainEvent) -> None:
        if fail_ids is None or event.id in fail_ids:
            raise RuntimeError("handler failed")

    return registry


async def test_committed_event_is_delivered_once_and_marked_published(
    sessionmaker: Sessionmaker,
) -> None:
    registry, delivered = _recording_registry()
    event = _event({"spec_id": "s-1"})
    await _commit_events(sessionmaker, [event])

    result = await relay_once(sessionmaker, registry=registry)

    assert result == RelayResult(published=1, failed=0, dead=0)
    assert delivered == [event]
    published_at, attempts = await _row(sessionmaker, event.id)
    assert published_at is not None
    assert attempts == 0


async def test_event_in_rolled_back_transaction_is_never_delivered(
    sessionmaker: Sessionmaker,
) -> None:
    registry, delivered = _recording_registry()
    async with sessionmaker() as session:
        await session.begin()
        add_event(session, _event())
        await session.rollback()

    result = await relay_once(sessionmaker, registry=registry)

    assert result == RelayResult(published=0, failed=0, dead=0)
    assert delivered == []


async def test_concurrent_relays_deliver_each_event_exactly_once(
    sessionmaker: Sessionmaker,
) -> None:
    registry, delivered = _recording_registry()
    events = [_event({"n": n}) for n in range(OVER_ONE_BATCH)]
    await _commit_events(sessionmaker, events)

    results = await asyncio.gather(
        relay_once(sessionmaker, registry=registry),
        relay_once(sessionmaker, registry=registry),
    )
    leftover = await relay_once(sessionmaker, registry=registry)

    counts = Counter(e.id for e in delivered)
    assert set(counts) == {e.id for e in events}
    assert max(counts.values()) == 1
    assert sum(r.published for r in results) + leftover.published == OVER_ONE_BATCH


async def test_failing_handler_leaves_event_unpublished_and_retries(
    sessionmaker: Sessionmaker,
) -> None:
    event = _event()
    await _commit_events(sessionmaker, [event])

    first = await relay_once(sessionmaker, registry=_failing_registry())
    second = await relay_once(sessionmaker, registry=_failing_registry())

    assert first == RelayResult(published=0, failed=1, dead=0)
    assert second == RelayResult(published=0, failed=1, dead=0)
    published_at, attempts = await _row(sessionmaker, event.id)
    assert published_at is None
    assert attempts == 2


async def test_one_failing_event_does_not_block_the_rest_of_the_batch(
    sessionmaker: Sessionmaker,
) -> None:
    bad, good = _event({"bad": True}), _event({"bad": False})
    await _commit_events(sessionmaker, [bad, good])

    result = await relay_once(sessionmaker, registry=_failing_registry({bad.id}))

    assert result == RelayResult(published=1, failed=1, dead=0)
    good_published_at, _ = await _row(sessionmaker, good.id)
    assert good_published_at is not None


async def test_event_stops_retrying_after_max_attempts_with_error_log(
    sessionmaker: Sessionmaker,
) -> None:
    event = _event()
    await _commit_events(sessionmaker, [event])
    registry = _failing_registry()

    with capture_logs() as logs:
        results = [await relay_once(sessionmaker, registry=registry) for _ in range(MAX_ATTEMPTS)]
    after_limit = await relay_once(sessionmaker, registry=registry)

    assert results[-1] == RelayResult(published=0, failed=0, dead=1)
    assert after_limit == RelayResult(published=0, failed=0, dead=0)
    _, attempts = await _row(sessionmaker, event.id)
    assert attempts == MAX_ATTEMPTS
    dead = [entry for entry in logs if entry["event"] == "outbox.event_dead"]
    assert len(dead) == 1
    assert dead[0]["log_level"] == "error"
    assert dead[0]["event_id"] == str(event.id)
    assert dead[0]["event_type"] == DomainEventType.SPEC_CONFIRMED
    assert dead[0]["workspace_id"] == str(WORKSPACE_ID)
    assert dead[0]["attempts"] == MAX_ATTEMPTS


async def test_event_without_handlers_is_marked_published(sessionmaker: Sessionmaker) -> None:
    event = _event()
    await _commit_events(sessionmaker, [event])

    result = await relay_once(sessionmaker, registry=EventRegistry())

    assert result == RelayResult(published=1, failed=0, dead=0)
    published_at, _ = await _row(sessionmaker, event.id)
    assert published_at is not None


async def test_relay_takes_one_batch_in_creation_order(sessionmaker: Sessionmaker) -> None:
    registry, delivered = _recording_registry()
    events = [_event({"n": n}) for n in range(OVER_ONE_BATCH)]
    await _commit_events(sessionmaker, events)

    first = await relay_once(sessionmaker, registry=registry)

    oldest = sorted(events, key=lambda e: (e.created_at, e.id))[:RELAY_BATCH_SIZE]
    assert first.published == RELAY_BATCH_SIZE
    assert [e.id for e in delivered] == [e.id for e in oldest]


async def test_undecodable_event_counts_as_failure_and_does_not_block_batch(
    sessionmaker: Sessionmaker,
) -> None:
    registry, delivered = _recording_registry()
    good = _event()
    bad_id = uuid4()
    async with sessionmaker() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO core.outbox (id, workspace_id, type, payload, created_at) "
                "VALUES (:id, :ws, 'RenamedEvent', '{}', now() - interval '1 minute')"
            ),
            {"id": bad_id, "ws": WORKSPACE_ID},
        )
        add_event(session, good)

    result = await relay_once(sessionmaker, registry=registry)

    assert result == RelayResult(published=1, failed=1, dead=0)
    assert delivered == [good]
    bad_published_at, bad_attempts = await _row(sessionmaker, bad_id)
    assert bad_published_at is None
    assert bad_attempts == 1


async def test_every_handler_for_a_type_receives_the_event(sessionmaker: Sessionmaker) -> None:
    registry = EventRegistry()
    calls: list[str] = []

    @registry.on(DomainEventType.SPEC_CONFIRMED)
    async def first(event: DomainEvent) -> None:
        calls.append("first")

    @registry.on(DomainEventType.SPEC_CONFIRMED)
    async def second(event: DomainEvent) -> None:
        calls.append("second")

    await _commit_events(sessionmaker, [_event()])

    await relay_once(sessionmaker, registry=registry)

    assert calls == ["first", "second"]
