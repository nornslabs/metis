"""The ``run_graph`` job: start, interrupt, resume, finish, fail and cancel a run.

Seam: the job function, called as Arq would, with real Postgres (as ``metis_app``), real Redis
and the real checkpointer. A good test here checks what an outside observer sees: the run's row,
the events on its Redis stream and the checkpoint, never runner internals.
"""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.state import MetisState
from metis.agent.supervisor import Specialist
from metis.agent.tools.ask_user import ask_user, request_approval
from metis.core.errors import UpstreamError
from metis.core.events import STREAM_TTL_SECONDS, RunEventType, stream_key
from metis.core.run_control import cancel_key, lock_key
from metis.modules.ideas import Stage
from tests.agent.run_job_helpers import (
    QueuedRun,
    checkpoint_values,
    events_of,
    job_ctx,
    node_events,
    queued_run,
    run_job,
    run_row,
    statuses,
)

# The stub path visits the Interviewer twice (intake → interviewing → researching) and the
# Scorer twice (the Advisor sends the run back once).
FULL_PATH = [
    "interviewer",
    "interviewer",
    "researcher",
    "scorer",
    "advisor",
    "scorer",
    "architect",
    "planner",
    "integrator",
]
QUESTION = {"type": "question", "question": "Who pays for this?"}


async def _interviewer_that_asks(state: MetisState) -> dict[str, Any]:
    answer = await ask_user.ainvoke({"question": QUESTION["question"]})
    return {
        "stage": Stage.RESEARCHING,
        "summary": f"payer: {answer}",
        "step_count": state["step_count"] + 1,
    }


async def _integrator_that_asks(state: MetisState) -> dict[str, Any]:
    approved = await request_approval.ainvoke({"action": "create issues", "details": "12 issues"})
    return {
        "stage": Stage.EXPORTED if approved else Stage.PLANNING,
        "step_count": state["step_count"] + 1,
    }


def _raising(error: Exception) -> Any:
    async def node(state: MetisState) -> dict[str, Any]:
        raise error

    return node


@pytest.fixture
def ctx(
    redis: Redis, app_sessions: async_sessionmaker[AsyncSession], checkpointer: AsyncPostgresSaver
) -> dict[str, Any]:
    """A job context on the stub specialists (``checkpointer`` makes sure its tables exist)."""
    return job_ctx(redis, app_sessions)


# ------------------------------------------------------------------ happy path
async def test_a_stub_run_succeeds_and_streams_every_node_in_order(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any]
) -> None:
    run = await queued_run(engine)

    await run_job(ctx, run)

    row = await run_row(engine, run)
    events = await events_of(redis, run)
    assert (row.status, row.started, row.finished, row.error) == ("succeeded", True, True, None)
    assert statuses(events) == ["running", "succeeded"]
    assert events[0].type is RunEventType.RUN_STATUS
    assert events[-1].type is RunEventType.RUN_STATUS
    assert node_events(events) == [
        (kind, node) for node in FULL_PATH for kind in ("node_started", "node_finished")
    ]
    assert 0 < await redis.ttl(stream_key(str(run.run_id))) <= STREAM_TTL_SECONDS
    assert not await redis.exists(lock_key(run.run_id))


async def test_a_run_starts_from_its_ideas_stage(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any]
) -> None:
    run = await queued_run(engine, stage=Stage.PLANNING.value)

    await run_job(ctx, run)

    assert node_events(await events_of(redis, run)) == [
        ("node_started", "integrator"),
        ("node_finished", "integrator"),
    ]


# ------------------------------------------------------------ interrupt, resume
async def test_a_question_pauses_the_run_and_is_stored(
    engine: AsyncEngine,
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
) -> None:
    ctx = job_ctx(redis, app_sessions, {Specialist.INTERVIEWER: _interviewer_that_asks})
    run = await queued_run(engine)

    await run_job(ctx, run)

    row = await run_row(engine, run)
    events = await events_of(redis, run)
    assert (row.status, row.finished, row.pending_interrupt) == ("awaiting_user", False, QUESTION)
    assert [e.data for e in events if e.type is RunEventType.INTERRUPT] == [QUESTION]
    assert statuses(events) == ["running", "awaiting_user"]
    assert events[-1].data == {"status": "awaiting_user"}
    assert await redis.ttl(stream_key(str(run.run_id))) == -1  # not terminal: no TTL yet
    assert not await redis.exists(lock_key(run.run_id))


async def test_a_resume_continues_from_the_same_checkpoint_to_the_end(
    engine: AsyncEngine,
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
) -> None:
    ctx = job_ctx(redis, app_sessions, {Specialist.INTERVIEWER: _interviewer_that_asks})
    run = await queued_run(engine)
    await run_job(ctx, run)
    seen = len(await events_of(redis, run))

    await run_job(ctx, run, resume="developers")

    row = await run_row(engine, run)
    after = (await events_of(redis, run))[seen:]
    assert (row.status, row.pending_interrupt, row.error) == ("succeeded", None, None)
    assert statuses(after) == ["running", "succeeded"]
    assert node_events(after)[0] == ("node_started", "interviewer")  # the asking node, re-run
    assert (await checkpoint_values(run))["summary"].startswith("payer: developers")
    assert (await checkpoint_values(run))["stage"] == Stage.EXPORTED


@pytest.mark.parametrize("approved", [True, False])
async def test_an_approval_pauses_and_the_decision_resumes_the_run(
    engine: AsyncEngine,
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
    approved: bool,
) -> None:
    ctx = job_ctx(redis, app_sessions, {Specialist.INTEGRATOR: _integrator_that_asks})
    run = await queued_run(engine, stage=Stage.PLANNING.value)
    await run_job(ctx, run)
    approval = {"type": "approval", "action": "create issues", "details": "12 issues"}
    assert (await run_row(engine, run)).pending_interrupt == approval

    await run_job(ctx, run, resume=approved)

    row = await run_row(engine, run)
    if approved:
        assert row.status == "succeeded"
    else:  # refused: the stage stays ``planning``, so the Integrator asks again
        assert (row.status, row.pending_interrupt) == ("awaiting_user", approval)


# -------------------------------------------------------------- left untouched
async def test_a_resume_for_a_run_that_is_not_waiting_changes_nothing(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any]
) -> None:
    run = await queued_run(engine)

    await run_job(ctx, run, resume="surprise")

    assert (await run_row(engine, run)).status == "queued"
    assert await events_of(redis, run) == []


async def test_a_run_that_waits_for_the_user_is_not_run_without_an_answer(
    engine: AsyncEngine,
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
) -> None:
    ctx = job_ctx(redis, app_sessions, {Specialist.INTERVIEWER: _interviewer_that_asks})
    run = await queued_run(engine)
    await run_job(ctx, run)
    seen = len(await events_of(redis, run))

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "awaiting_user"
    assert len(await events_of(redis, run)) == seen


async def test_a_finished_run_is_left_alone(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any]
) -> None:
    run = await queued_run(engine)
    await run_job(ctx, run)
    seen = len(await events_of(redis, run))

    await run_job(ctx, run)
    await run_job(ctx, run, resume="late")

    assert (await run_row(engine, run)).status == "succeeded"
    assert len(await events_of(redis, run)) == seen


async def test_an_unknown_run_is_ignored(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any]
) -> None:
    run = await queued_run(engine)
    ghost = QueuedRun(run_id=run.workspace_id, workspace_id=run.workspace_id)

    await run_job(ctx, ghost)

    assert (await run_row(engine, run)).status == "queued"


# ------------------------------------------------------------------------ lock
async def test_a_run_whose_lock_is_held_is_not_touched(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any]
) -> None:
    run = await queued_run(engine)
    await redis.set(lock_key(run.run_id), "another-worker", ex=60)

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "queued"
    assert await events_of(redis, run) == []
    assert await redis.get(lock_key(run.run_id)) == b"another-worker"


# --------------------------------------------------------------------- failure
async def test_a_raising_node_fails_the_run_without_leaking_the_exception_text(
    engine: AsyncEngine,
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
) -> None:
    boom = _raising(RuntimeError("secret sk-live-123 in a traceback"))
    ctx = job_ctx(redis, app_sessions, {Specialist.RESEARCHER: boom})
    run = await queued_run(engine)

    await run_job(ctx, run)

    row = await run_row(engine, run)
    events = await events_of(redis, run)
    error = {"code": "run.failed", "message": "Run Failed"}
    assert (row.status, row.finished, row.error) == ("failed", True, error)
    assert statuses(events) == ["running", "failed"]
    assert events[-1].data == {"status": "failed", "error": error}
    assert "sk-live-123" not in repr(row) + repr(events)
    assert await redis.ttl(stream_key(str(run.run_id))) > 0
    assert not await redis.exists(lock_key(run.run_id))


async def test_a_domain_error_keeps_its_code(
    engine: AsyncEngine,
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
) -> None:
    boom = _raising(UpstreamError("exa said: key sk-1 rejected", meta={"provider": "exa"}))
    ctx = job_ctx(redis, app_sessions, {Specialist.RESEARCHER: boom})
    run = await queued_run(engine)

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None
    assert row.error["code"] == "provider.upstream_error"
    assert "sk-1" not in repr(row)


async def test_the_workspaces_step_limit_ends_the_run_as_failed(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any]
) -> None:
    run = await queued_run(engine)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO identity.workspace_settings "
                "(workspace_id, run_budget_usd, max_steps, version) VALUES (:ws, 2.00, 3, 1)"
            ),
            {"ws": run.workspace_id},
        )

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error == {"code": "run.step_limit_reached", "message": "Run Step Limit Reached"}
    nodes = [
        node for kind, node in node_events(await events_of(redis, run)) if kind == "node_started"
    ]
    assert nodes == ["interviewer", "interviewer", "researcher"]  # three steps, then the stop


# ---------------------------------------------------------------------- cancel
async def test_a_cancel_flag_set_before_the_start_cancels_the_queued_run(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any]
) -> None:
    run = await queued_run(engine)
    await redis.set(cancel_key(run.run_id), "1", ex=60)

    await run_job(ctx, run)

    row = await run_row(engine, run)
    events = await events_of(redis, run)
    assert (row.status, row.finished) == ("cancelled", True)
    assert statuses(events) == ["cancelled"]
    assert node_events(events) == []


async def test_a_cancel_flag_set_mid_run_stops_it_at_the_next_step(
    engine: AsyncEngine,
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
) -> None:
    run = await queued_run(engine)

    async def researcher_then_cancel(state: MetisState) -> dict[str, Any]:
        await redis.set(cancel_key(run.run_id), "1", ex=60)
        return {"stage": Stage.SCORING, "step_count": state["step_count"] + 1}

    ctx = job_ctx(redis, app_sessions, {Specialist.RESEARCHER: researcher_then_cancel})

    await run_job(ctx, run)

    row = await run_row(engine, run)
    events = await events_of(redis, run)
    assert (row.status, row.finished) == ("cancelled", True)
    assert statuses(events) == ["running", "cancelled"]
    assert "scorer" not in [node for _, node in node_events(events)]
    assert (await checkpoint_values(run))["stage"] == Stage.SCORING  # the checkpoint stays
    assert await redis.ttl(stream_key(str(run.run_id))) > 0
