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
from metis.agent.specialists.stubs import stub_specialists
from metis.agent.supervisor import Specialist
from metis.core.events import RunEvent, RunEventType, read
from metis.helpers.http import ClientFactory
from metis.jobs.run_graph import run_graph
from tests.agent.graph_helpers import APP_DATABASE_URL
from tests.agent.interview_helpers import ScriptedLLM
from tests.agent.llm_helpers import make_run, workspace_with_key, workspace_without_key


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


async def keyed_run(engine: AsyncEngine, sub: str = "ada", stage: str = "intake") -> QueuedRun:
    """A queued run in a workspace with an LLM key saved."""
    workspace_id = await workspace_with_key(engine, sub)
    return QueuedRun(await make_run(engine, workspace_id, stage), workspace_id)


def job_ctx(
    redis: Redis,
    sessions: async_sessionmaker[AsyncSession],
    specialists: Any = None,
    *,
    llm: ScriptedLLM | None = None,
    exa: ClientFactory | None = None,
    score: bool = False,
    advise: bool = False,
    architect: bool = False,
    planner: bool = False,
    oauth: ClientFactory | None = None,
    mcp: Any = None,
) -> dict[str, Any]:
    """The Arq ``ctx`` a worker would pass, with the runner pointed at the test database.

    Without ``llm`` every specialist is a stub unless ``specialists`` replaces it. With
    ``llm`` the real specialists run against that scripted model; the Researcher stays a stub
    unless ``exa`` (the Exa HTTP client factory, e.g. a ``FakeExaMcp`` transport) is given, and
    the Scorer stays a stub unless ``score`` is true, the Advisor unless ``advise`` is, and the
    Architect unless ``architect`` is, and the Planner unless ``planner`` is. ``oauth`` and
    ``mcp`` route a Linear token refresh and Linear's MCP sessions to a fake.
    """
    if llm is None:
        specialists = {**stub_specialists(), **(specialists or {})}
    else:
        stubs = stub_specialists()
        kept = {} if score else {Specialist.SCORER: stubs[Specialist.SCORER]}
        if not advise:
            kept[Specialist.ADVISOR] = stubs[Specialist.ADVISOR]
        if not architect:
            kept[Specialist.ARCHITECT] = stubs[Specialist.ARCHITECT]
        if not planner:
            kept[Specialist.PLANNER] = stubs[Specialist.PLANNER]
        if exa is None:
            kept[Specialist.RESEARCHER] = stubs[Specialist.RESEARCHER]
        specialists = {**kept, **(specialists or {})}
    deps = RunnerDeps(
        sessions=sessions,
        database_url=APP_DATABASE_URL,
        specialists=specialists,
        llm_http_client=llm.client if llm else None,
        exa_http_client=exa,
        oauth_http_client=oauth,
        mcp_http_client=mcp,
    )
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


async def idea_stage(engine: AsyncEngine, run: QueuedRun) -> str:
    """The stage saved on the run's idea (``ideas.ideas.stage``)."""
    async with engine.connect() as conn:
        stage = await conn.scalar(
            text(
                "SELECT stage FROM ideas.ideas "
                "WHERE id = (SELECT idea_id FROM ideas.workflow_runs WHERE id = :id)"
            ),
            {"id": run.run_id},
        )
    return str(stage)


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
