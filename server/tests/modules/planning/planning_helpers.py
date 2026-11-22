"""Setup helpers for the planning tests: plan inputs, a saved plan, and what the DB holds."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.modules import planning
from metis.modules.planning import DepInput, PhaseInput, Plan, PlanInput, TaskInput
from tests.modules.ideas.idea_helpers import IDEAS_URL, Caller, owner
from tests.modules.ideas.spec_helpers import draft_idea
from tests.modules.scoring.scoring_helpers import Sessions, in_workspace


def task(key: str, phase: int = 0, estimate: int = 3, **fields: Any) -> TaskInput:
    """One valid task (title from the key); ``fields`` override it."""
    values: dict[str, Any] = {
        "key": key,
        "phase": phase,
        "title": f"Task {key}",
        "estimate": estimate,
    }
    values.update(fields)
    return TaskInput(**values)


def dep(task_key: str, blocked_by_key: str) -> DepInput:
    return DepInput(task_key=task_key, blocked_by_key=blocked_by_key)


def plan_input(
    tasks: list[TaskInput] | None = None, deps: list[DepInput] | None = None, phases: int = 2
) -> PlanInput:
    """A plan of ``phases`` phases; by default tasks a, b in phase 0 and c in phase 1, c after a."""
    if tasks is None:
        tasks = [task("a"), task("b", estimate=5), task("c", phase=1, estimate=2)]
        deps = [dep("c", "a")] if deps is None else deps
    return PlanInput(
        phases=tuple(
            PhaseInput(name=f"Phase {i}", goal=f"Goal {i}", exit_criteria=f"Done {i}")
            for i in range(phases)
        ),
        tasks=tuple(tasks),
        deps=tuple(deps or ()),
    )


async def latest_spec_id(client: httpx.AsyncClient, caller: Caller, idea_id: str) -> UUID:
    """The id of the idea's latest spec version."""
    response = await client.get(f"{IDEAS_URL}/{idea_id}/spec", headers=caller.headers)
    assert response.status_code == 200, response.text
    return UUID(response.json()["latest"]["id"])


async def save(
    sessions: Sessions,
    caller: Caller,
    idea_id: str,
    spec_version_id: UUID,
    data: PlanInput | None = None,
) -> Plan:
    """Save a plan through the service (the Planner's path) in a committed transaction."""
    workspace_id = UUID(caller.workspace_id)
    async with in_workspace(sessions, workspace_id) as session:
        return await planning.save_plan(
            session,
            workspace_id,
            UUID(idea_id),
            spec_version_id,
            plan_input() if data is None else data,
        )


async def planned(
    client: httpx.AsyncClient, engine: AsyncEngine, sessions: Sessions
) -> tuple[Caller, dict[str, str], UUID, Plan]:
    """An owner, their idea with a spec, the spec version id, and a saved default plan."""
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, sessions, ada)
    spec_id = await latest_spec_id(client, ada, idea["id"])
    return ada, idea, spec_id, await save(sessions, ada, idea["id"], spec_id)


def plan_url(plan_id: UUID | str, tail: str = "") -> str:
    return f"/v1/plans/{plan_id}{tail}"


def task_id(plan: Plan, title: str) -> UUID:
    """The id of the task titled ``Task <key>``."""
    return next(t.id for p in plan.phases for t in p.tasks if t.title == f"Task {title}")


def titles(plan: dict[str, Any]) -> list[list[str]]:
    """Task titles per phase of a plan response, in order."""
    return [[t["title"] for t in phase["tasks"]] for phase in plan["phases"]]


async def plan_ready_events(engine: AsyncEngine, caller: Caller) -> list[dict[str, Any]]:
    """The workspace's ``PlanReady`` payloads, oldest first (read as the DB owner)."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT payload FROM core.outbox WHERE workspace_id = :ws "
                "AND type = 'PlanReady' ORDER BY id"
            ),
            {"ws": caller.workspace_id},
        )
    return [dict(row[0]) for row in result]
