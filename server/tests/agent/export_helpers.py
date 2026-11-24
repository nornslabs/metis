"""Setup and read-back helpers for the Integrator (export preview) tests."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.specialists.integrator import build_integrator
from metis.agent.state import initial_state
from metis.agent.supervisor import Specialist
from metis.helpers.ids import uuid7
from metis.modules import ideas, planning
from metis.modules.ideas import NewSpecVersion, SpecSource, Stage
from tests.agent.linear_helpers import mcp_client, oauth_client
from tests.agent.planner_helpers import idea_of
from tests.agent.run_job_helpers import QueuedRun, job_ctx, queued_run
from tests.helpers.fake_linear import FakeLinear
from tests.modules.scoring.scoring_helpers import in_workspace

TOOLS = (
    "list_teams",
    "list_issue_labels",
    "create_issue_label",
    "save_project",
    "save_milestone",
    "save_issue",
)
PHASE_NAMES = ["Foundations", "Core", "Launch"]


def _plan() -> planning.PlanInput:
    phases = tuple(
        planning.PhaseInput(name=name, goal=f"Do {name}.", exit_criteria=f"{name} done.")
        for name in PHASE_NAMES
    )
    tasks = (
        planning.TaskInput(key="a", phase=0, title="Task a", estimate=3, labels=("backend",)),
        planning.TaskInput(
            key="b", phase=1, title="Task b", estimate=5, labels=("backend", "Frontend")
        ),
        planning.TaskInput(key="c", phase=2, title="Task c", estimate=2),
    )
    deps = (
        planning.DepInput(task_key="b", blocked_by_key="a"),
        planning.DepInput(task_key="c", blocked_by_key="b"),
    )
    return planning.PlanInput(phases=phases, tasks=tasks, deps=deps)


async def export_run(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    *,
    plan: bool = True,
    confirm: bool = True,
    sub: str = "ada",
    plan_input: planning.PlanInput | None = None,
) -> QueuedRun:
    """A queued run on an idea at ``planning`` with a confirmed spec and (by default) a saved
    draft plan of three phases, three tasks and two blocked-by links."""
    run = await queued_run(engine, sub, stage="spec_draft")
    idea_id = await idea_of(engine, run)
    if confirm:
        async with in_workspace(sessions, run.workspace_id) as session:
            await ideas.save_spec_version(
                session,
                run.workspace_id,
                idea_id,
                NewSpecVersion(content_md="## Problem\n\nLeads get lost.", source=SpecSource.AGENT),
            )
            await ideas.confirm_spec(session, run.workspace_id, idea_id, 1)
            overview = await ideas.get_spec_overview(session, run.workspace_id, idea_id)
            if plan:
                assert overview.confirmed is not None
                await planning.save_plan(
                    session, run.workspace_id, idea_id, overview.confirmed.id, plan_input or _plan()
                )
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE ideas.ideas SET stage = 'planning' WHERE id = :id"), {"id": idea_id}
        )
    return run


def export_ctx(
    redis: Redis, sessions: async_sessionmaker[AsyncSession], linear: FakeLinear
) -> dict[str, Any]:
    """The job context with the real Integrator pointed at the fake Linear (other nodes stubs)."""
    node = build_integrator(
        lambda ws: in_workspace(sessions, ws), redis, oauth_client(linear), mcp_client(linear)
    )
    return job_ctx(redis, sessions, specialists={Specialist.INTEGRATOR: node})


async def owner_of(engine: AsyncEngine, run: QueuedRun) -> UUID:
    async with engine.connect() as conn:
        value = await conn.scalar(
            text("SELECT created_by FROM identity.workspaces WHERE id = :ws"),
            {"ws": run.workspace_id},
        )
    assert isinstance(value, UUID)
    return value


async def approval(
    engine: AsyncEngine, run: QueuedRun, *, approved: bool, plan_version: int = 1
) -> dict[str, Any]:
    """The resume value the API sends for an export approval: it stamps ``decided_by`` and the
    plan version the preview showed (a fresh plan is version 1)."""
    return {
        "approved": approved,
        "decided_by": str(await owner_of(engine, run)),
        "plan_version": plan_version,
    }


async def bump_plan_version(engine: AsyncEngine, run: QueuedRun) -> None:
    """Change the run's plan after the preview (an edit bumps its version)."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE planning.plans SET version = version + 1 WHERE idea_id = "
                "(SELECT idea_id FROM ideas.workflow_runs WHERE id = :run)"
            ),
            {"run": run.run_id},
        )


async def external_refs(engine: AsyncEngine, run: QueuedRun) -> dict[tuple[str, UUID], str]:
    """The workspace's Linear refs as ``{(local_kind, local_id): external_id}``."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT local_kind, local_id, external_id FROM integrations.external_refs "
                "WHERE workspace_id = :ws AND provider = 'linear'"
            ),
            {"ws": run.workspace_id},
        )
        return {(row[0], row[1]): row[2] for row in result.all()}


async def save_team(engine: AsyncEngine, run: QueuedRun, team_id: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO identity.workspace_settings "
                "(workspace_id, run_budget_usd, max_steps, linear_team_id) "
                "VALUES (:ws, 2, 50, :team)"
            ),
            {"ws": run.workspace_id, "team": team_id},
        )


async def saved_team(engine: AsyncEngine, run: QueuedRun) -> str | None:
    async with engine.connect() as conn:
        value = await conn.scalar(
            text("SELECT linear_team_id FROM identity.workspace_settings WHERE workspace_id = :ws"),
            {"ws": run.workspace_id},
        )
    return None if value is None else str(value)


async def export_jobs(engine: AsyncEngine, run: QueuedRun) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT status, decided_by, plan_id, summary FROM integrations.export_jobs "
                "WHERE run_id = :run"
            ),
            {"run": run.run_id},
        )
        return [dict(row._mapping) for row in result.all()]


async def plan_status(engine: AsyncEngine, run: QueuedRun) -> str:
    async with engine.connect() as conn:
        value = await conn.scalar(
            text(
                "SELECT p.status FROM planning.plans p "
                "JOIN ideas.workflow_runs r ON r.idea_id = p.idea_id WHERE r.id = :run"
            ),
            {"run": run.run_id},
        )
    return str(value)


async def add_refs(engine: AsyncEngine, run: QueuedRun, kind: str, local_ids: list[UUID]) -> None:
    async with engine.begin() as conn:
        for local_id in local_ids:
            await conn.execute(
                text(
                    "INSERT INTO integrations.external_refs "
                    "(id, workspace_id, provider, local_kind, local_id, external_id) "
                    "VALUES (gen_random_uuid(), :ws, 'linear', :kind, :local, 'ext')"
                ),
                {"ws": run.workspace_id, "kind": kind, "local": local_id},
            )


async def local_ids(engine: AsyncEngine, run: QueuedRun, table: str) -> list[UUID]:
    """Ids of the plan's ``phases`` or ``tasks`` in plan order."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                f"SELECT t.id FROM planning.{table} t JOIN planning.plans p ON p.id = t.plan_id "
                "JOIN ideas.workflow_runs r ON r.idea_id = p.idea_id WHERE r.id = :run "
                "ORDER BY t.position"
            ),
            {"run": run.run_id},
        )
        return [row[0] for row in result.all()]


async def reopen_job(engine: AsyncEngine, run: QueuedRun) -> None:
    """Put the run's export job back to ``running``, as it is after a crash before it was ended
    (the node run again on the same run then carries on with the writes)."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE integrations.export_jobs SET status = 'running', finished_at = NULL "
                "WHERE run_id = :run"
            ),
            {"run": run.run_id},
        )


async def next_run(engine: AsyncEngine, run: QueuedRun) -> QueuedRun:
    """A new queued run on the same idea (what "export again" starts once the first has ended)."""
    run_id = uuid7()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ideas.workflow_runs (id, workspace_id, idea_id) "
                "VALUES (:id, :ws, :idea)"
            ),
            {"id": run_id, "ws": run.workspace_id, "idea": await idea_of(engine, run)},
        )
    return QueuedRun(run_id, run.workspace_id)


async def rerun_node(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    redis: Redis,
    linear: FakeLinear,
    run: QueuedRun,
    monkeypatch: pytest.MonkeyPatch,
    *,
    reopen: bool = True,
) -> dict[str, Any]:
    """Run the node again on the same run: the recorded decision is found, nothing is asked, the
    writes carry on (what the job does after a crash). ``reopen`` first puts a finished job back
    to ``running``, as a crash before it was ended would have left it."""
    if reopen:
        await reopen_job(engine, run)
    node = build_integrator(
        lambda ws: in_workspace(sessions, ws), redis, oauth_client(linear), mcp_client(linear)
    )

    def refuse_to_ask(*_: Any, **__: Any) -> Any:
        raise AssertionError("a re-run must not interrupt")

    monkeypatch.setattr("metis.agent.specialists.integrator.interrupt", refuse_to_ask)
    monkeypatch.setattr(
        "metis.agent.specialists.integrator.get_stream_writer", lambda: lambda _event: None
    )
    state = initial_state(
        run_id=run.run_id,
        workspace_id=run.workspace_id,
        idea_id=await idea_of(engine, run),
        stage=Stage.PLANNING,
        max_steps=50,
    )
    return await node(state)


async def outbox_count(engine: AsyncEngine, run: QueuedRun, event_type: str) -> int:
    async with engine.connect() as conn:
        value = await conn.scalar(
            text("SELECT count(*) FROM core.outbox WHERE workspace_id = :ws AND type = :type"),
            {"ws": run.workspace_id, "type": event_type},
        )
    return int(value or 0)
