"""Helpers for the ``run_graph`` job tests: a workspace with a queued run, the job context,
and what an outside observer sees (the run row, the event stream, the checkpoint)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.checkpoint import open_checkpointer
from metis.agent.graph import build_graph
from metis.agent.runner import RunnerDeps
from metis.core.events import RunEvent, RunEventType, read
from metis.jobs.run_graph import run_graph
from tests.agent.graph_helpers import APP_DATABASE_URL
from tests.agent.llm_helpers import make_run, workspace_without_key


@dataclass(frozen=True)
class RunRow:
    status: str
    started: bool
    finished: bool
    error: dict[str, Any] | None
    pending_interrupt: dict[str, Any] | None


@dataclass(frozen=True)
class QueuedRun:
    run_id: UUID
    workspace_id: UUID


async def queued_run(engine: AsyncEngine, sub: str = "ada", stage: str = "intake") -> QueuedRun:
    workspace_id = await workspace_without_key(engine, sub)
    return QueuedRun(await make_run(engine, workspace_id, stage), workspace_id)


def job_ctx(
    redis: Redis, sessions: async_sessionmaker[AsyncSession], specialists: Any = None
) -> dict[str, Any]:
    """The Arq ``ctx`` a worker would pass, with the runner pointed at the test database."""
    deps = RunnerDeps(sessions=sessions, database_url=APP_DATABASE_URL, specialists=specialists)
    return {"redis": redis, "run_deps": deps}


async def run_job(ctx: dict[str, Any], run: QueuedRun, resume: Any = None) -> None:
    await run_graph(ctx, run_id=str(run.run_id), workspace_id=str(run.workspace_id), resume=resume)


async def run_row(engine: AsyncEngine, run: QueuedRun) -> RunRow:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT status, started_at IS NOT NULL, finished_at IS NOT NULL, error, "
                    "pending_interrupt FROM ideas.workflow_runs WHERE id = :id"
                ),
                {"id": run.run_id},
            )
        ).one()
    return RunRow(*row)


async def events_of(redis: Redis, run: QueuedRun) -> list[RunEvent]:
    return [event async for event in read(str(run.run_id), redis=redis)]


def statuses(events: list[RunEvent]) -> list[str]:
    return [e.data["status"] for e in events if e.type is RunEventType.RUN_STATUS]


def node_events(events: list[RunEvent]) -> list[tuple[str, str]]:
    """``(type, node)`` of the node_started / node_finished events, in order."""
    kinds = {RunEventType.NODE_STARTED, RunEventType.NODE_FINISHED}
    return [(e.type.value, e.data["node"]) for e in events if e.type in kinds]


async def checkpoint_values(run: QueuedRun) -> dict[str, Any]:
    """The run's last checkpoint, read through a brand-new graph and pool."""
    async with open_checkpointer(APP_DATABASE_URL) as saver:
        graph = build_graph(saver)
        snapshot = await graph.aget_state({"configurable": {"thread_id": str(run.run_id)}})
    return dict(snapshot.values)
