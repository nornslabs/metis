"""Runs one agent run end to end: the body of the ``run_graph`` job.

Under the run's Redis lock the runner loads the run, moves it to ``running``, drives the
graph (``thread_id`` = run id), publishes its events and settles the run's status:

- every stage a node sets is copied to ``ideas.stage`` (``agent/stage_sync.py``), so a later
  run starts where this one stopped;
- the graph ends → ``succeeded``, or ``failed`` when it set ``last_error`` (the step limit);
- the graph pauses on ``interrupt()`` → ``awaiting_user`` with the question stored;
- the API set ``cancel:{run_id}`` → ``cancelled`` at the next step boundary;
- anything raises → ``failed`` with a stable error code (never the raw exception text).

It starts a new run from the idea's stage, resumes a paused one with ``Command(resume=...)``,
and continues a crashed one from its last checkpoint. Each run gets its own ``LLMGateway``
(closed when the stream ends); the Interviewer, Researcher and Scorer are real, the other
specialists are stubs, and ``AGENT_STUB_SPECIALISTS`` makes every specialist a stub. No database
transaction is open while the graph runs: every status change is its own short, committed
transaction, and the terminal ``run_status`` event is published after its row is committed.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from typing import Any, Literal
from uuid import UUID

import httpx
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, StreamMode
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis.agent.checkpoint import open_checkpointer
from metis.agent.graph import CompiledGraph, build_graph
from metis.agent.llm import LLMGateway
from metis.agent.run_events import RunEventPublisher
from metis.agent.run_lock import RunLock, hold_run_lock
from metis.agent.specialists.interviewer import build_interviewer
from metis.agent.specialists.researcher import build_researcher
from metis.agent.specialists.scorer import build_scorer
from metis.agent.specialists.stubs import SpecialistNode
from metis.agent.stage_sync import save_stage, stages_in
from metis.agent.state import initial_state
from metis.agent.supervisor import Specialist
from metis.core.config import get_settings
from metis.core.db import get_session_maker, set_workspace
from metis.core.errors import ERROR_CATALOG, ErrorCode, MetisError
from metis.core.events import RunEventType
from metis.core.logging import get_logger
from metis.core.run_control import cancel_requested
from metis.helpers.http import ClientFactory, provider_http_factory
from metis.modules import ideas, identity
from metis.modules.ideas import RunStatus, Stage, WorkflowRun
from metis.modules.ideas.helpers.run_transitions import TERMINAL_STATUSES

# Each step's checkpoint is written before the next step starts, so a killed worker (or a
# cancel) loses no completed step.
# The stream includes subgraphs: LangGraph only streams the model output of a specialist's
# own tool-calling loop (a subgraph) when asked to.
STREAM_MODES: list[StreamMode] = ["updates", "messages", "custom", "tasks"]

logger = get_logger(__name__)


@dataclass(frozen=True)
class RunnerDeps:
    """What the runner talks to besides Redis; tests replace them (nodes, test database, LLM).

    ``specialists`` replaces nodes by specialist (over the real ones and the stubs);
    ``llm_http_client`` makes the HTTP client each run's chat models use; ``exa_http_client`` makes
    the one the Researcher's Exa session uses (default: the shared provider client).
    """

    sessions: async_sessionmaker[AsyncSession]
    database_url: str
    specialists: Mapping[Specialist, SpecialistNode] | None = None
    llm_http_client: Callable[[], httpx.AsyncClient] | None = None
    exa_http_client: ClientFactory | None = None


def default_deps() -> RunnerDeps:
    return RunnerDeps(sessions=get_session_maker(), database_url=get_settings().database_url)


@dataclass(frozen=True)
class Outcome:
    """How a stream ended."""

    kind: Literal["done", "interrupted", "cancelled", "lock_lost"]
    interrupt: dict[str, Any] | None = None
    last_error: str | None = None


async def execute_run(
    redis: Redis,
    run_id: UUID,
    workspace_id: UUID,
    resume: Any = None,
    *,
    deps: RunnerDeps | None = None,
) -> None:
    """Run ``run_id`` until it finishes, pauses for the user, is cancelled or fails.

    A run whose lock another worker holds, one already finished, and a resume for a run
    that is not waiting for the user are all left untouched.
    """
    deps = deps or default_deps()
    settings = get_settings()
    async with hold_run_lock(
        redis,
        run_id,
        ttl_seconds=settings.run_lock_ttl_seconds,
        heartbeat_seconds=settings.run_lock_heartbeat_seconds,
    ) as lock:
        if not lock.acquired:
            logger.info("run.lock_held")
            return
        run = await _load(deps, workspace_id, run_id)
        if run is None or not _should_run(run, resume):
            return
        publisher = RunEventPublisher(str(run_id), redis)
        if await cancel_requested(redis, run_id):
            await _settle(deps, publisher, run, Outcome("cancelled"))
            return
        try:
            await _drive(deps, redis, publisher, lock, run, resume)
        except Exception as exc:  # noqa: BLE001  (every failure is recorded on the run)
            await _fail(deps, publisher, run, exc)


async def _drive(
    deps: RunnerDeps,
    redis: Redis,
    publisher: RunEventPublisher,
    lock: RunLock,
    run: WorkflowRun,
    resume: Any,
) -> None:
    async with _scoped(deps, run.workspace_id) as session:
        await ideas.mark_running(session, run.workspace_id, run.id)
    await publisher.status(RunStatus.RUNNING.value)
    logger.info("run.started", resumed=resume is not None)
    async with publisher.flushing():
        outcome = await _stream(deps, redis, publisher, lock, run, resume)
    await _settle(deps, publisher, run, outcome)


async def _stream(
    deps: RunnerDeps,
    redis: Redis,
    publisher: RunEventPublisher,
    lock: RunLock,
    run: WorkflowRun,
    resume: Any,
) -> Outcome:
    gateway = LLMGateway(
        run.workspace_id,
        run.id,
        sessions=deps.sessions,
        http_client=deps.llm_http_client() if deps.llm_http_client else None,
    )
    try:
        return await _stream_graph(deps, redis, publisher, lock, run, resume, gateway)
    finally:
        await gateway.aclose()


async def _stream_graph(
    deps: RunnerDeps,
    redis: Redis,
    publisher: RunEventPublisher,
    lock: RunLock,
    run: WorkflowRun,
    resume: Any,
    gateway: LLMGateway,
) -> Outcome:
    async with open_checkpointer(deps.database_url) as saver:
        graph = build_graph(saver, specialists=_specialists(deps, gateway, redis))
        config: RunnableConfig = {"configurable": {"thread_id": str(run.id)}}
        await _sync_checkpoint_stage(graph, config, deps, run)
        payload = await _input(graph, config, deps, run, resume)
        interrupt: dict[str, Any] | None = None
        async for namespace, mode, chunk in graph.astream(
            payload, config, stream_mode=STREAM_MODES, durability="sync", subgraphs=True
        ):
            if lock.lost:
                return Outcome("lock_lost")
            if namespace and mode != "messages":
                continue  # a specialist's inner loop: only its model output is published
            if mode == "updates" and isinstance(chunk, Mapping):
                await _save_stages(deps, run, chunk)
            interrupt = interrupt or await publisher.handle(mode, chunk)
            if mode == "updates" and await cancel_requested(redis, run.id):
                return Outcome("cancelled")
        if interrupt is not None:
            return Outcome("interrupted", interrupt=interrupt)
        final = (await graph.aget_state(config)).values
        return Outcome("done", last_error=final.get("last_error"))


async def _sync_checkpoint_stage(
    graph: CompiledGraph, config: RunnableConfig, deps: RunnerDeps, run: WorkflowRun
) -> None:
    """Save the checkpoint's stage on the idea before (re)starting a run.

    The checkpoint is written before the runner sees a node's ``updates`` chunk, so a crash
    in between leaves ``ideas.stage`` one step behind; this catches it up.
    """
    stage = (await graph.aget_state(config)).values.get("stage")
    if stage is None:
        return
    async with _scoped(deps, run.workspace_id) as session:
        await save_stage(session, run.workspace_id, run.idea_id, Stage(stage))


async def _save_stages(deps: RunnerDeps, run: WorkflowRun, update: Mapping[str, Any]) -> None:
    """Copy the stage a node just set to ``ideas.stage``, in its own short transaction."""
    for stage in stages_in(update):
        async with _scoped(deps, run.workspace_id) as session:
            await save_stage(session, run.workspace_id, run.idea_id, stage)


def _specialists(
    deps: RunnerDeps, gateway: LLMGateway, redis: Redis
) -> Mapping[Specialist, SpecialistNode]:
    """The real specialists (none with ``AGENT_STUB_SPECIALISTS``), then ``deps`` overrides."""
    real: dict[Specialist, SpecialistNode] = {}
    if not get_settings().agent_stub_specialists:
        real[Specialist.INTERVIEWER] = build_interviewer(gateway, partial(_scoped, deps))
        real[Specialist.RESEARCHER] = build_researcher(
            gateway,
            partial(_scoped, deps),
            redis,
            deps.exa_http_client or provider_http_factory(),
        )
        real[Specialist.SCORER] = build_scorer(
            gateway,
            partial(_scoped, deps),
            redis,
            deps.exa_http_client or provider_http_factory(),
        )
    return {**real, **(deps.specialists or {})}


async def _input(
    graph: CompiledGraph, config: RunnableConfig, deps: RunnerDeps, run: WorkflowRun, resume: Any
) -> Any:
    """What to feed the graph: the answer, nothing (continue a checkpoint) or a fresh start."""
    if resume is not None:
        return Command(resume=resume)
    if (await graph.aget_state(config)).values:
        return None  # crash recovery: continue from the last checkpoint
    async with _scoped(deps, run.workspace_id) as session:
        idea = await ideas.get_idea(session, run.workspace_id, run.idea_id)
        overview = await identity.get_settings_overview(session, run.workspace_id)
    return initial_state(
        run_id=run.id,
        workspace_id=run.workspace_id,
        idea_id=idea.id,
        stage=idea.stage,
        max_steps=overview.settings.max_steps,
    )


async def _settle(
    deps: RunnerDeps, publisher: RunEventPublisher, run: WorkflowRun, outcome: Outcome
) -> None:
    """Record how the stream ended on the run, then publish it (after the commit)."""
    ws, run_id = run.workspace_id, run.id
    if outcome.kind == "lock_lost":
        logger.warning("run.stopped_lock_lost")  # another worker owns the run now
        return
    if outcome.kind == "interrupted":
        assert outcome.interrupt is not None
        async with _scoped(deps, ws) as session:
            await ideas.mark_awaiting_user(session, ws, run_id, outcome.interrupt)
        await publisher.publish(RunEventType.INTERRUPT, outcome.interrupt)
        await publisher.status(RunStatus.AWAITING_USER.value)
    elif outcome.kind == "cancelled":
        async with _scoped(deps, ws) as session:
            await ideas.mark_cancelled(session, ws, run_id)
        await publisher.status(RunStatus.CANCELLED.value)
    elif outcome.last_error:
        await _record_failure(deps, publisher, run, _error(outcome.last_error))
    else:
        async with _scoped(deps, ws) as session:
            await ideas.mark_succeeded(session, ws, run_id)
        await publisher.status(RunStatus.SUCCEEDED.value)
    logger.info("run.settled", outcome=outcome.kind)


async def _fail(
    deps: RunnerDeps, publisher: RunEventPublisher, run: WorkflowRun, exc: Exception
) -> None:
    code = exc.code if isinstance(exc, MetisError) else ErrorCode.RUN_FAILED
    logger.exception("run.failed", code=code.value)
    try:
        await _record_failure(deps, publisher, run, _error(code.value))
    except Exception:  # noqa: BLE001
        # Leave the run as it is; crash recovery or the user's next action takes it from here.
        logger.exception("run.failure_not_recorded")


async def _record_failure(
    deps: RunnerDeps, publisher: RunEventPublisher, run: WorkflowRun, error: dict[str, str]
) -> None:
    async with _scoped(deps, run.workspace_id) as session:
        await ideas.mark_failed(session, run.workspace_id, run.id, error)
    await publisher.status(RunStatus.FAILED.value, error=error)


def _error(code: str) -> dict[str, str]:
    """``{code, message}`` with the catalog's title: never raw exception text."""
    try:
        title = ERROR_CATALOG[ErrorCode(code)].title
    except ValueError:
        title = ERROR_CATALOG[ErrorCode.RUN_FAILED].title
    return {"code": code, "message": title}


async def _load(deps: RunnerDeps, workspace_id: UUID, run_id: UUID) -> WorkflowRun | None:
    async with _scoped(deps, workspace_id) as session:
        try:
            return await ideas.get_run(session, workspace_id, run_id)
        except MetisError:
            logger.warning("run.not_found")
            return None


def _should_run(run: WorkflowRun, resume: Any) -> bool:
    if run.status in TERMINAL_STATUSES:
        logger.info("run.already_finished", status=run.status.value)
        return False
    if resume is not None and run.status != RunStatus.AWAITING_USER:
        logger.warning("run.resume_ignored", status=run.status.value)
        return False
    if resume is None and run.status == RunStatus.AWAITING_USER:
        logger.info("run.awaiting_answer")
        return False
    return True


@asynccontextmanager
async def _scoped(deps: RunnerDeps, workspace_id: UUID) -> AsyncGenerator[AsyncSession]:
    """One short transaction scoped to the workspace; committed when the block ends."""
    async with deps.sessions() as session, session.begin():
        await set_workspace(session, workspace_id)
        yield session
