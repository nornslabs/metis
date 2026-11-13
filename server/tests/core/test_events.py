"""Tests for the run event bus: ``publish`` / ``read`` over Redis Streams.

The single seam is the public API of ``metis.core.events`` against a real Redis.
Tests assert only what a caller sees: returned ids, yielded events, their order,
blocking-read timing and the stream TTL.

Set ``TEST_REDIS_URL`` to point at a Redis instance; tests skip when none is
reachable.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from metis.core import events
from metis.core.errors import MetisError
from metis.core.events import (
    STREAM_MAXLEN,
    STREAM_TTL_SECONDS,
    RunEvent,
    RunEventType,
    publish,
    read,
)

REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
RUN_ID = "run-1"
STREAM_KEY = f"run:{RUN_ID}"
BLOCK_MS = 2000
SHORT_BLOCK_MS = 200
PUBLISH_DELAY_SECONDS = 0.1


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[Redis]:
    client: Redis = Redis.from_url(REDIS_URL)
    try:
        await client.ping()
    except Exception:  # noqa: BLE001
        await client.aclose()
        pytest.skip("Redis not reachable")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


async def _collect(
    redis: Redis, after_id: str = "0", block_ms: int | None = None
) -> list[RunEvent]:
    return [e async for e in read(RUN_ID, after_id, block_ms, redis=redis)]


async def _publish_three(redis: Redis) -> list[str]:
    return [
        await publish(RUN_ID, RunEventType.NODE_STARTED, {"node": "scout"}, redis=redis),
        await publish(RUN_ID, RunEventType.TOKEN, {"text": "hi"}, redis=redis),
        await publish(RUN_ID, RunEventType.NODE_FINISHED, {"node": "scout"}, redis=redis),
    ]


@pytest.mark.asyncio
async def test_events_read_from_start_in_order_with_stable_ids(redis: Redis) -> None:
    ids = await _publish_three(redis)

    got = await _collect(redis)

    assert [e.id for e in got] == ids
    assert [e.type for e in got] == [
        RunEventType.NODE_STARTED,
        RunEventType.TOKEN,
        RunEventType.NODE_FINISHED,
    ]
    assert got[1].data == {"text": "hi"}
    assert all(e.run_id == RUN_ID for e in got)
    assert await _collect(redis) == got


@pytest.mark.asyncio
async def test_read_after_id_returns_only_later_events(redis: Redis) -> None:
    ids = await _publish_three(redis)

    got = await _collect(redis, after_id=ids[1])

    assert [e.id for e in got] == [ids[2]]


@pytest.mark.asyncio
async def test_read_of_missing_stream_yields_nothing(redis: Redis) -> None:
    assert await _collect(redis) == []


@pytest.mark.asyncio
async def test_blocking_read_returns_when_new_event_arrives(redis: Redis) -> None:
    ids = await _publish_three(redis)

    async def publish_later() -> str:
        await asyncio.sleep(PUBLISH_DELAY_SECONDS)
        return await publish(RUN_ID, RunEventType.TOOL_CALL, {"tool": "exa"}, redis=redis)

    started = time.monotonic()
    publisher = asyncio.create_task(publish_later())
    got = await _collect(redis, after_id=ids[-1], block_ms=BLOCK_MS)
    elapsed_ms = (time.monotonic() - started) * 1000

    assert [e.id for e in got] == [await publisher]
    assert elapsed_ms < BLOCK_MS


@pytest.mark.asyncio
async def test_blocking_read_with_no_new_events_times_out_empty(redis: Redis) -> None:
    ids = await _publish_three(redis)

    started = time.monotonic()
    got = await _collect(redis, after_id=ids[-1], block_ms=SHORT_BLOCK_MS)
    elapsed_ms = (time.monotonic() - started) * 1000

    assert got == []
    assert elapsed_ms >= SHORT_BLOCK_MS * 0.9


@pytest.mark.asyncio
async def test_terminal_run_status_sets_stream_ttl(redis: Redis) -> None:
    await publish(RUN_ID, RunEventType.RUN_STATUS, {"status": "running"}, redis=redis)
    await publish(RUN_ID, RunEventType.TOKEN, {"text": "x"}, redis=redis)
    assert await redis.ttl(STREAM_KEY) == -1

    await publish(RUN_ID, RunEventType.RUN_STATUS, {"status": "succeeded"}, redis=redis)

    ttl = await redis.ttl(STREAM_KEY)
    assert STREAM_TTL_SECONDS - 5 <= ttl <= STREAM_TTL_SECONDS
    assert STREAM_TTL_SECONDS == 24 * 60 * 60


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "cancelled"])
async def test_other_terminal_statuses_set_ttl(redis: Redis, status: str) -> None:
    await publish(RUN_ID, RunEventType.RUN_STATUS, {"status": status}, redis=redis)

    assert await redis.ttl(STREAM_KEY) > 0


@pytest.mark.asyncio
async def test_stream_is_capped_near_maxlen(redis: Redis) -> None:
    overflow = 500
    pipe = redis.pipeline()
    for _ in range(STREAM_MAXLEN + overflow):
        pipe.xadd(STREAM_KEY, {"type": "token", "data": "{}", "ts": "2026-01-01T00:00:00+00:00"})
    await pipe.execute()

    await publish(RUN_ID, RunEventType.TOKEN, {"text": "x"}, redis=redis)

    assert STREAM_MAXLEN <= await redis.xlen(STREAM_KEY) < STREAM_MAXLEN + overflow
    assert STREAM_MAXLEN == 5000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"type": "nope", "data": "{}", "ts": "2026-01-01T00:00:00+00:00"},
        {"type": "token", "data": "{not json", "ts": "2026-01-01T00:00:00+00:00"},
        {"type": "token", "data": "[1, 2]", "ts": "2026-01-01T00:00:00+00:00"},
        {"type": "token", "ts": "2026-01-01T00:00:00+00:00"},
    ],
)
async def test_malformed_entry_raises_domain_error(redis: Redis, fields: dict[str, str]) -> None:
    await redis.xadd(STREAM_KEY, fields)  # type: ignore[arg-type]

    with pytest.raises(MetisError):
        await _collect(redis)


@pytest.mark.asyncio
async def test_publish_without_client_uses_redis_url(
    redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    from metis.core.config import get_settings

    monkeypatch.setenv("REDIS_URL", REDIS_URL)
    get_settings.cache_clear()

    event_id = await publish(RUN_ID, RunEventType.TOKEN, {"text": "x"})
    got = [e async for e in read(RUN_ID)]

    assert [e.id for e in got] == [event_id]
    assert events.stream_key(RUN_ID) == STREAM_KEY
