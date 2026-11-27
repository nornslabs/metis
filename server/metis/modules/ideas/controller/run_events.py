"""``GET /v1/runs/{run_id}/events``: a run's events as Server-Sent Events.

The route checks the run (workspace, RLS, archived idea) and releases its database session
before the first byte, so a stream holds no connection while it waits. Events come straight
from ``core.events``; the Redis entry id is the SSE ``id``, so ``Last-Event-ID`` is a stream
position. The stream closes after a terminal ``run_status``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Query
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from metis.core import events
from metis.core.config import get_settings
from metis.core.db import SessionDep
from metis.core.errors import MalformedEventError
from metis.core.logging import get_logger
from metis.helpers import sse
from metis.modules.ideas import service
from metis.modules.ideas.dto import RunView
from metis.modules.identity import StreamWorkspaceDep

router = APIRouter()
logger = get_logger(__name__)

READ_BLOCK_MS = 15_000  # one blocking read; a quiet read sends a ping, so this is the heartbeat


@router.get(
    "/runs/{run_id}/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "Run event stream"}},
)
async def stream_run_events(
    session: SessionDep,
    workspace: StreamWorkspaceDep,
    run_id: UUID,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    after: Annotated[str | None, Query(description="Resume after this event id")] = None,
) -> StreamingResponse:
    """Stream the run's events from ``Last-Event-ID`` (or ``after``), else from the start."""
    after_id = _start_position(last_event_id, after)
    view = await service.workflow_runs.get_run_view(session, workspace.workspace.id, run_id)
    frames = stream_frames(
        str(run_id),
        after_id,
        run_finished=_is_finished(view),
        outcome=_outcome(view),
    )
    return StreamingResponse(frames, media_type="text/event-stream", headers=sse.SSE_HEADERS)


async def stream_frames(
    run_id: str,
    after_id: str,
    *,
    run_finished: bool,
    outcome: dict[str, Any] | None = None,
) -> AsyncGenerator[str]:
    """The SSE frames of ``run_id`` after ``after_id``.

    A run that is already finished is read once without waiting. When its stream is gone, one
    ``run_status`` frame built from ``outcome`` (no ``id``) tells the client how it ended.
    """
    yield sse.RETRY_FRAME
    # Own client: the shared one has a 0.5 s socket timeout, shorter than a blocking read.
    client: Redis = Redis.from_url(get_settings().redis_url)
    try:
        if (
            run_finished
            and outcome is not None
            and not await client.exists(events.stream_key(run_id))
        ):
            yield sse.json_frame(
                "run_status",
                {
                    "run_id": run_id,
                    "type": "run_status",
                    "data": outcome,
                    "ts": datetime.now(UTC).isoformat(),
                },
            )
            return
        while True:
            seen = False
            try:
                async for event in events.read(
                    run_id, after_id, None if run_finished else READ_BLOCK_MS, redis=client
                ):
                    seen = True
                    after_id = event.id
                    yield sse.format_frame(event.type.value, event.model_dump_json(), event.id)
                    if _is_terminal_event(event):
                        return
            except MalformedEventError as exc:
                logger.error(
                    "run.event_malformed", run_id=run_id, after_id=after_id, error=str(exc)
                )
                yield sse.json_frame("error", {"code": "run.event_malformed"})
                return
            if run_finished:
                return
            if not seen:
                yield sse.PING_FRAME
    finally:
        await client.aclose()


def _start_position(last_event_id: str | None, after: str | None) -> str:
    if last_event_id:
        return sse.parse_stream_id(last_event_id, field="header.Last-Event-ID")
    if after:
        return sse.parse_stream_id(after, field="query.after")
    return events.STREAM_START_ID


def _is_finished(view: RunView) -> bool:
    return view.status.value in events.TERMINAL_RUN_STATUSES


def _outcome(view: RunView) -> dict[str, Any]:
    outcome: dict[str, Any] = {"status": view.status.value}
    if view.error is not None:
        outcome["error"] = view.error
    return outcome


def _is_terminal_event(event: events.RunEvent) -> bool:
    return (
        event.type is events.RunEventType.RUN_STATUS
        and event.data.get("status") in events.TERMINAL_RUN_STATUSES
    )
