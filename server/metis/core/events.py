"""Run event bus over Redis Streams.

The worker publishes ordered run events with :func:`publish`; the API reads
them with :func:`read` and streams them over SSE. Each run has one stream,
``run:{run_id}``. The Redis entry id is the SSE event id, so ``Last-Event-ID``
maps straight to a stream position. Streams are capped at about
:data:`STREAM_MAXLEN` entries and expire :data:`STREAM_TTL_SECONDS` after a
terminal ``run_status`` event.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError
from redis.asyncio import Redis

from metis.core.config import get_settings
from metis.core.errors import MalformedEventError

STREAM_KEY_PREFIX = "run:"
STREAM_MAXLEN = 5000
STREAM_TTL_SECONDS = 24 * 60 * 60
STREAM_START_ID = "0"

# RunStatus values after which a run never emits again.
# TODO(runs module): use the RunStatus enum once it exists.
TERMINAL_RUN_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


class RunEventType(StrEnum):
    """Kinds of event a run emits."""

    NODE_STARTED = "node_started"
    NODE_FINISHED = "node_finished"
    TOKEN = "token"
    TOOL_CALL = "tool_call"
    INTERRUPT = "interrupt"
    RUN_STATUS = "run_status"


class RunEvent(BaseModel):
    """One event read back from a run's stream."""

    model_config = ConfigDict(frozen=True)

    id: str
    run_id: str
    type: RunEventType
    data: dict[str, Any]
    ts: datetime


def stream_key(run_id: str) -> str:
    """Redis key of the stream holding ``run_id``'s events."""
    return f"{STREAM_KEY_PREFIX}{run_id}"


@asynccontextmanager
async def _client(redis: Redis | None) -> AsyncGenerator[Redis]:
    """Yield ``redis`` as is, or open a client from ``REDIS_URL`` and close it after."""
    if redis is not None:
        yield redis
        return
    owned: Redis = Redis.from_url(get_settings().redis_url)
    try:
        yield owned
    finally:
        await owned.aclose()


def _is_terminal(event_type: RunEventType, data: Mapping[str, Any]) -> bool:
    return event_type is RunEventType.RUN_STATUS and data.get("status") in TERMINAL_RUN_STATUSES


async def publish(
    run_id: str,
    type: RunEventType,  # noqa: A002 - matches the event envelope field name
    data: Mapping[str, Any],
    *,
    redis: Redis | None = None,
) -> str:
    """Append an event to ``run_id``'s stream and return its id.

    A ``run_status`` event with a terminal status also sets the stream to
    expire after :data:`STREAM_TTL_SECONDS`, in the same transaction. Pass
    ``redis`` to reuse an open client; it is never closed here.
    """
    event_type = RunEventType(type)
    fields = {
        "type": event_type.value,
        "data": json.dumps(dict(data)),
        "ts": datetime.now(UTC).isoformat(),
    }
    key = stream_key(run_id)
    async with _client(redis) as client, client.pipeline(transaction=True) as pipe:
        pipe.xadd(key, fields, maxlen=STREAM_MAXLEN, approximate=True)  # type: ignore[arg-type]
        if _is_terminal(event_type, data):
            pipe.expire(key, STREAM_TTL_SECONDS)
        results = await pipe.execute()
    return _text(results[0])


async def read(
    run_id: str,
    after_id: str = STREAM_START_ID,
    block_ms: int | None = None,
    *,
    redis: Redis | None = None,
) -> AsyncIterator[RunEvent]:
    """Yield ``run_id``'s events after ``after_id``, in publish order.

    Runs a single ``XREAD``. With ``block_ms``, waits up to that many
    milliseconds for new events and yields nothing on timeout. Callers that
    stream (the SSE endpoint) call this in a loop, passing the last id seen.

    Raises:
        MalformedEventError: an entry is missing a field, has an unknown type
            or carries data that is not a JSON object.
    """
    async with _client(redis) as client:
        response = await client.xread({stream_key(run_id): after_id}, block=block_ms)
    for _key, entries in response or []:
        for entry_id, fields in entries:
            yield _decode(run_id, _text(entry_id), fields)


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _decode(run_id: str, event_id: str, raw: Mapping[bytes | str, bytes | str]) -> RunEvent:
    fields = {_text(k): _text(v) for k, v in raw.items()}
    try:
        return RunEvent.model_validate(
            {
                "id": event_id,
                "run_id": run_id,
                "type": fields["type"],
                "data": json.loads(fields["data"]),
                "ts": fields["ts"],
            }
        )
    except (KeyError, json.JSONDecodeError, ValidationError) as exc:
        raise MalformedEventError(
            f"Malformed event {event_id} in stream {stream_key(run_id)}"
        ) from exc


__all__ = [
    "STREAM_MAXLEN",
    "STREAM_TTL_SECONDS",
    "MalformedEventError",
    "RunEvent",
    "RunEventType",
    "publish",
    "read",
    "stream_key",
]
