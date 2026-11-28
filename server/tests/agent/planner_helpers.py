"""Setup and read-back helpers for the Planner tests."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.modules import ideas, planning
from metis.modules.ideas import NewSpecVersion, SpecSource
from tests.agent.interview_helpers import Reply
from tests.agent.run_job_helpers import QueuedRun, keyed_run
from tests.agent.score_helpers import call, save_snapshot
from tests.modules.scoring.scoring_helpers import in_workspace

PHASES = [
    {"name": "Foundations", "goal": "Set up the base.", "exit_criteria": "Base runs."},
    {"name": "Core", "goal": "Build the core.", "exit_criteria": "Core works."},
    {"name": "Launch", "goal": "Ship it.", "exit_criteria": "Users can sign up."},
]


def brief(key: str) -> str:
    """A minimal valid issue brief for task ``key``."""
    return (
        f"## Goal\nDeliver {key}.\n\n## Requirements\n1. Build {key}.\n\n"
        f"## Acceptance criteria\n- {key} works."
    )


def task(
    key: str, phase: int, estimate: int = 3, blocked_by: tuple[str, ...] = ()
) -> dict[str, Any]:
    return {
        "key": key,
        "phase": phase,
        "title": f"Task {key}",
        "description": brief(key),
        "estimate": estimate,
        "labels": ["backend"],
        "blocked_by": list(blocked_by),
    }


TASKS = [task("a", 0), task("b", 1, 5, ("a",)), task("c", 2, 2, ("b",))]


def propose(phases: list[dict[str, str]] | None = None) -> Reply:
    return call("propose_phases", phases=phases if phases is not None else PHASES)


def save_plan(tasks: list[dict[str, Any]] | None = None) -> Reply:
    return call("save_plan", tasks=tasks if tasks is not None else TASKS)


async def planning_run(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], *, confirm: bool = True
) -> QueuedRun:
    """A run on an idea whose spec is confirmed (``spec_confirmed``), with research done."""
    run = await keyed_run(engine, stage="spec_draft")
    await save_snapshot(engine, run)
    if confirm:
        idea_id = await idea_of(engine, run)
        async with in_workspace(app_sessions, run.workspace_id) as session:
            await ideas.save_spec_version(
                session,
                run.workspace_id,
                idea_id,
                NewSpecVersion(content_md="## Problem\n\nLeads get lost.", source=SpecSource.AGENT),
            )
            await ideas.confirm_spec(session, run.workspace_id, idea_id, 1)
    return run


async def idea_of(engine: AsyncEngine, run: QueuedRun) -> UUID:
    async with engine.connect() as conn:
        value = await conn.scalar(
            text("SELECT idea_id FROM ideas.workflow_runs WHERE id = :id"), {"id": run.run_id}
        )
    assert isinstance(value, UUID)
    return value


async def stored_plans(engine: AsyncEngine, run: QueuedRun) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT p.id, p.status, p.version, p.spec_version_id FROM planning.plans p "
                "JOIN ideas.workflow_runs r ON r.idea_id = p.idea_id WHERE r.id = :run"
            ),
            {"run": run.run_id},
        )
        return [dict(row._mapping) for row in result.all()]


async def stored_phases(engine: AsyncEngine, run: QueuedRun) -> list[str]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT h.name FROM planning.phases h JOIN planning.plans p ON p.id = h.plan_id "
                "JOIN ideas.workflow_runs r ON r.idea_id = p.idea_id WHERE r.id = :run "
                "ORDER BY h.position"
            ),
            {"run": run.run_id},
        )
        return [row[0] for row in result.all()]


async def stored_tasks(engine: AsyncEngine, run: QueuedRun) -> list[tuple[str, str, int]]:
    """``(phase name, task title, estimate)`` in plan order."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT h.name, t.title, t.estimate FROM planning.tasks t "
                "JOIN planning.phases h ON h.id = t.phase_id "
                "JOIN planning.plans p ON p.id = t.plan_id "
                "JOIN ideas.workflow_runs r ON r.idea_id = p.idea_id WHERE r.id = :run "
                "ORDER BY h.position, t.position"
            ),
            {"run": run.run_id},
        )
        return [(row[0], row[1], row[2]) for row in result.all()]


async def stored_dep_count(engine: AsyncEngine, run: QueuedRun) -> int:
    async with engine.connect() as conn:
        count = await conn.scalar(
            text(
                "SELECT count(*) FROM planning.task_deps d "
                "JOIN planning.plans p ON p.id = d.plan_id "
                "JOIN ideas.workflow_runs r ON r.idea_id = p.idea_id WHERE r.id = :run"
            ),
            {"run": run.run_id},
        )
    return int(count or 0)


async def save_existing_plan(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], run: QueuedRun
) -> None:
    """A draft plan for the idea's confirmed spec, as an earlier visit of the Planner left it."""
    idea_id = await idea_of(engine, run)
    async with in_workspace(app_sessions, run.workspace_id) as session:
        overview = await ideas.get_spec_overview(session, run.workspace_id, idea_id)
        assert overview.confirmed is not None
        data = planning.PlanInput(
            phases=tuple(planning.PhaseInput.model_validate(p) for p in PHASES),
            tasks=(planning.TaskInput(key="a", phase=0, title="Task a", estimate=3),),
        )
        await planning.save_plan(session, run.workspace_id, idea_id, overview.confirmed.id, data)
