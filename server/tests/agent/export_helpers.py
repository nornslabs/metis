"""Setup and read-back helpers for the Integrator (export preview) tests."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.specialists.integrator import build_integrator
from metis.agent.supervisor import Specialist
from metis.modules import ideas, planning
from metis.modules.ideas import NewSpecVersion, SpecSource
from tests.agent.linear_helpers import mcp_client, oauth_client
from tests.agent.planner_helpers import idea_of
from tests.agent.run_job_helpers import QueuedRun, job_ctx, queued_run
from tests.helpers.fake_linear import FakeLinear
from tests.modules.scoring.scoring_helpers import in_workspace

TOOLS = ("list_teams", "list_issue_labels", "save_project", "save_milestone", "save_issue")
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
                    session, run.workspace_id, idea_id, overview.confirmed.id, _plan()
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


async def approval(engine: AsyncEngine, run: QueuedRun, *, approved: bool) -> dict[str, Any]:
    """The resume value the API sends for an export approval (it stamps ``decided_by``)."""
    return {"approved": approved, "decided_by": str(await owner_of(engine, run))}


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
