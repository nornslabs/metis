"""``GET /v1/runs/{id}/events`` (SSE) at the HTTP seam.

Real app, Postgres (request session as ``metis_app``, so RLS applies) and Redis; events are
published with ``core.events.publish``. ``httpx.ASGITransport`` returns a response only once
the stream has ended, so every stream here ends on a terminal ``run_status`` (or a closing
rule) and the tests read the whole body. Idle and live cases publish from a background task.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from idea_helpers import Caller, create, member_of, owner
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.core import events, jobs
from metis.core.config import get_settings
from metis.core.events import RunEventType
from metis.modules.ideas.controller import run_events
from tests.helpers.auth import assert_problem, auth, sign_in
from tests.modules.conftest import REDIS_URL

STATUS = RunEventType.RUN_STATUS
TOKEN = RunEventType.TOKEN
FAST_BLOCK_MS = 50


@pytest.fixture(autouse=True)
def _no_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(jobs, "enqueue", noop)
    # stream_frames opens its own Redis client from settings; align it with the test redis fixture.
    test_settings = get_settings().model_copy(update={"redis_url": REDIS_URL})
    monkeypatch.setattr(run_events, "get_settings", lambda: test_settings)


async def _new_run(client: httpx.AsyncClient, caller: Caller, title: str = "Pocket CRM") -> str:
    idea = await create(client, caller, title=title)
    response = await client.post(
        f"/v1/ideas/{idea['id']}/runs", headers={**caller.headers, "Idempotency-Key": uuid4().hex}
    )
    assert response.status_code == 202, response.text
    return str(response.json()["run_id"])


async def _set_status(engine: AsyncEngine, run_id: str, status: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE ideas.workflow_runs SET status = :s WHERE id = :id"),
            {"s": status, "id": run_id},
        )


async def _publish(
    redis: Redis, run_id: str, *items: tuple[RunEventType, dict[str, Any]]
) -> list[str]:
    return [await events.publish(run_id, kind, data, redis=redis) for kind, data in items]


def _frames(body: str) -> list[dict[str, str]]:
    """Parse an SSE body into one dict per frame (``id``, ``event``, ``data``, ``retry``)."""
    frames = []
    for block in body.split("\n\n"):
        fields = {}
        for line in block.splitlines():
            name, _, value = line.partition(":")
            fields[name or "comment"] = value.strip()
        if fields:
            frames.append(fields)
    return frames


def _events(body: str) -> list[dict[str, str]]:
    return [f for f in _frames(body) if "event" in f]


async def _stream(
    client: httpx.AsyncClient,
    caller: Caller,
    run_id: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> httpx.Response:
    return await client.get(
        f"/v1/runs/{run_id}/events", headers={**caller.headers, **(headers or {})}, params=params
    )


async def test_it_replays_events_in_order_with_their_redis_ids_and_ends_on_a_terminal_status(
    client: httpx.AsyncClient, engine: AsyncEngine, redis: Redis
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(client, ada)
    ids = await _publish(
        redis,
        run_id,
        (TOKEN, {"text": "hi"}),
        (STATUS, {"status": "running"}),
        (STATUS, {"status": "succeeded"}),
    )

    response = await _stream(client, ada, run_id)

    assert response.status_code == 200
    got = _events(response.text)
    assert [f["id"] for f in got] == ids
    assert [f["event"] for f in got] == ["token", "run_status", "run_status"]
    assert '"status":"succeeded"' in got[-1]["data"].replace(" ", "")


@pytest.mark.parametrize("status", ["succeeded", "failed", "cancelled"])
async def test_the_stream_ends_after_each_terminal_status(
    client: httpx.AsyncClient, engine: AsyncEngine, redis: Redis, status: str
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(client, ada)
    await _publish(redis, run_id, (STATUS, {"status": status}))

    response = await _stream(client, ada, run_id)

    assert [f["event"] for f in _events(response.text)] == ["run_status"]


async def test_last_event_id_resumes_exactly_after_that_event(
    client: httpx.AsyncClient, engine: AsyncEngine, redis: Redis
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(client, ada)
    ids = await _publish(
        redis,
        run_id,
        (TOKEN, {"n": 1}),
        (TOKEN, {"n": 2}),
        (TOKEN, {"n": 3}),
        (STATUS, {"status": "succeeded"}),
    )

    response = await _stream(client, ada, run_id, headers={"Last-Event-ID": ids[1]})

    assert [f["id"] for f in _events(response.text)] == ids[2:]


async def test_the_after_query_resumes_like_the_header_and_the_header_wins(
    client: httpx.AsyncClient, engine: AsyncEngine, redis: Redis
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(client, ada)
    ids = await _publish(
        redis, run_id, (TOKEN, {"n": 1}), (TOKEN, {"n": 2}), (STATUS, {"status": "succeeded"})
    )

    by_query = await _stream(client, ada, run_id, params={"after": ids[0]})
    both = await _stream(
        client, ada, run_id, headers={"Last-Event-ID": ids[1]}, params={"after": ids[0]}
    )

    assert [f["id"] for f in _events(by_query.text)] == ids[1:]
    assert [f["id"] for f in _events(both.text)] == ids[2:]


async def test_an_event_published_after_connecting_is_delivered(
    client: httpx.AsyncClient, engine: AsyncEngine, redis: Redis
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(client, ada)

    async def publish_later() -> None:
        await asyncio.sleep(0.2)
        await _publish(redis, run_id, (TOKEN, {"text": "late"}), (STATUS, {"status": "succeeded"}))

    task = asyncio.create_task(publish_later())
    response = await _stream(client, ada, run_id)
    await task

    assert [f["event"] for f in _events(response.text)] == ["token", "run_status"]


async def test_an_idle_stream_sends_pings_and_a_retry_hint(
    client: httpx.AsyncClient, engine: AsyncEngine, redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_events, "READ_BLOCK_MS", FAST_BLOCK_MS)
    ada = await owner(client, engine)
    run_id = await _new_run(client, ada)

    async def finish_later() -> None:
        await asyncio.sleep(0.4)
        await _publish(redis, run_id, (STATUS, {"status": "succeeded"}))

    task = asyncio.create_task(finish_later())
    response = await _stream(client, ada, run_id)
    await task

    assert response.text.count(": ping") >= 2
    assert response.text.startswith("retry: 3000")


async def test_the_response_has_the_streaming_headers(
    client: httpx.AsyncClient, engine: AsyncEngine, redis: Redis
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(client, ada)
    await _publish(redis, run_id, (STATUS, {"status": "failed"}))

    response = await _stream(client, ada, run_id)

    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


@pytest.mark.parametrize("bad", ["abc", "1-", "-1", "1-2-3", "1 2", "$"])
async def test_a_malformed_last_event_id_or_after_is_422_before_streaming(
    client: httpx.AsyncClient, engine: AsyncEngine, bad: str
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(client, ada)

    by_header = await _stream(client, ada, run_id, headers={"Last-Event-ID": bad})
    by_query = await _stream(client, ada, run_id, params={"after": bad})

    assert_problem(by_header, 422, "common.validation_failed")
    assert_problem(by_query, 422, "common.validation_failed")


async def test_a_foreign_unknown_or_archived_run_is_404_and_no_session_is_401(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine, "ada")
    grace = await owner(client, engine, "grace")
    run_id = await _new_run(client, ada)
    archived_idea = await create(client, ada, title="Archived")
    archived_run = (
        await client.post(
            f"/v1/ideas/{archived_idea['id']}/runs",
            headers={**ada.headers, "Idempotency-Key": uuid4().hex},
        )
    ).json()["run_id"]
    await client.delete(f"/v1/ideas/{archived_idea['id']}", headers=ada.headers)

    for caller, target in [(grace, run_id), (ada, str(uuid4())), (ada, archived_run)]:
        assert_problem(await _stream(client, caller, target), 404, "run.not_found")
    unsigned = await client.get(f"/v1/runs/{run_id}/events")
    assert_problem(unsigned, 401, "auth.not_signed_in")


async def test_the_workspace_query_finds_a_run_in_another_workspace_and_a_foreign_one_is_403(
    client: httpx.AsyncClient, engine: AsyncEngine, redis: Redis
) -> None:
    ada = await owner(client, engine, "ada")
    bob = await member_of(client, engine, ada, "bob")
    outsider = await sign_in(engine, "eve", "eve@example.com", "Eve")
    run_id = await _new_run(client, ada)
    await _publish(redis, run_id, (STATUS, {"status": "succeeded"}))
    cookie_only = auth(bob.token)  # personal workspace by default: the run is not visible there

    default = await client.get(f"/v1/runs/{run_id}/events", headers=cookie_only)
    named = await client.get(
        f"/v1/runs/{run_id}/events", headers=cookie_only, params={"workspace_id": ada.workspace_id}
    )
    foreign = await client.get(
        f"/v1/runs/{run_id}/events",
        headers=auth(outsider),
        params={"workspace_id": ada.workspace_id},
    )
    header_wins = await client.get(
        f"/v1/runs/{run_id}/events",
        headers=auth(bob.token, ada.workspace_id),
        params={"workspace_id": str(uuid4())},
    )

    assert_problem(default, 404, "run.not_found")
    assert named.status_code == 200
    assert [f["event"] for f in _events(named.text)] == ["run_status"]
    assert_problem(foreign, 403, "auth.forbidden")
    assert header_wins.status_code == 200


async def test_a_finished_run_with_no_stream_sends_one_status_frame_without_an_id(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(client, ada)
    await _set_status(engine, run_id, "succeeded")

    response = await _stream(client, ada, run_id)

    got = _events(response.text)
    assert len(got) == 1
    assert got[0]["event"] == "run_status"
    assert "id" not in got[0]
    assert '"status":"succeeded"' in got[0]["data"].replace(" ", "")
    # The web client validates the envelope; without `ts` it drops the frame and reconnects forever.
    assert set(json.loads(got[0]["data"])) == {"run_id", "type", "data", "ts"}


async def test_resuming_at_the_terminal_event_of_a_finished_run_closes_with_no_events(
    client: httpx.AsyncClient, engine: AsyncEngine, redis: Redis
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(client, ada)
    ids = await _publish(redis, run_id, (TOKEN, {"n": 1}), (STATUS, {"status": "succeeded"}))
    await _set_status(engine, run_id, "succeeded")

    at_terminal = await _stream(client, ada, run_id, headers={"Last-Event-ID": ids[1]})
    before_terminal = await _stream(client, ada, run_id, headers={"Last-Event-ID": ids[0]})

    assert _events(at_terminal.text) == []
    assert [f["id"] for f in _events(before_terminal.text)] == [ids[1]]


async def test_an_undecodable_entry_ends_the_stream_with_an_error_frame(
    client: httpx.AsyncClient, engine: AsyncEngine, redis: Redis
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(client, ada)
    await _publish(redis, run_id, (TOKEN, {"n": 1}))
    await redis.xadd(events.stream_key(run_id), {"type": "nonsense"})
    await _publish(redis, run_id, (STATUS, {"status": "succeeded"}))

    response = await _stream(client, ada, run_id)

    got = _events(response.text)
    assert [f["event"] for f in got] == ["token", "error"]
    assert "run.event_malformed" in got[-1]["data"]


async def test_closing_the_frame_generator_opens_no_more_reads(
    redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_events, "READ_BLOCK_MS", FAST_BLOCK_MS)
    run_id = str(uuid4())
    frames = run_events.stream_frames(run_id, events.STREAM_START_ID, run_finished=False)

    first = await anext(frames)  # the retry hint
    await frames.aclose()

    assert first.startswith("retry:")
    assert await redis.xlen(events.stream_key(run_id)) == 0
