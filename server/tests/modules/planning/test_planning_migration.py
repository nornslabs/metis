"""Migration ``0021_planning``: RLS, the checks and keys that keep a plan valid, deferrable
positions, and the single migration head."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.helpers.ids import uuid7
from tests.modules.planning.planning_helpers import planned, task_id
from tests.modules.scoring.scoring_helpers import Sessions

TABLES = ("plans", "phases", "tasks", "task_deps")
SERVER = Path(__file__).resolve().parents[3]


async def _execute(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)


def test_the_migration_chain_has_one_head() -> None:
    config = Config(str(SERVER / "alembic.ini"))
    config.set_main_option("script_location", str(SERVER / "migrations"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["0025_workspace_linear_team"]


async def test_every_planning_table_has_row_level_security(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'planning' "
                    "AND relkind = 'r'"
                )
            )
        ).all()

    assert {row[0]: (row[1], row[2]) for row in rows} == {t: (True, True) for t in TABLES}


@pytest.mark.parametrize("estimate", [0, 4, 13])
async def test_the_database_refuses_an_estimate_outside_the_fibonacci_set(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions, estimate: int
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    with pytest.raises(IntegrityError, match="ck_tasks_estimate"):
        await _execute(
            engine,
            "INSERT INTO planning.tasks (id, workspace_id, plan_id, phase_id, position, title, "
            "estimate) VALUES (:id, :ws, :plan, :phase, 9, 'x', :estimate)",
            id=uuid7(),
            ws=UUID(ada.workspace_id),
            plan=plan.id,
            phase=plan.phases[0].id,
            estimate=estimate,
        )


async def test_the_database_refuses_a_self_dependency_and_a_dangling_one(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)
    a = task_id(plan, "a")
    insert = (
        "INSERT INTO planning.task_deps (workspace_id, plan_id, task_id, blocked_by_task_id) "
        "VALUES (:ws, :plan, :task, :blocker)"
    )
    values = {"ws": UUID(ada.workspace_id), "plan": plan.id}

    with pytest.raises(IntegrityError, match="ck_task_deps_self"):
        await _execute(engine, insert, task=a, blocker=a, **values)
    with pytest.raises(IntegrityError, match="fk_task_deps_blocked_by_task_id_tasks"):
        await _execute(engine, insert, task=a, blocker=uuid7(), **values)


async def test_the_database_refuses_a_task_in_a_phase_that_is_not_in_the_plan(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    with pytest.raises(IntegrityError, match="fk_tasks_phase_id_phases"):
        await _execute(
            engine,
            "INSERT INTO planning.tasks (id, workspace_id, plan_id, phase_id, position, title, "
            "estimate) VALUES (:id, :ws, :plan, :phase, 9, 'x', 3)",
            id=uuid7(),
            ws=UUID(ada.workspace_id),
            plan=plan.id,
            phase=uuid7(),  # a phase that does not exist
        )


async def test_positions_are_unique_but_may_swap_inside_one_transaction(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    _, _, _, plan = await planned(client, engine, app_sessions)
    first, second = plan.phases[0].id, plan.phases[1].id

    with pytest.raises(IntegrityError, match="uq_phases_plan_position"):
        await _execute(engine, "UPDATE planning.phases SET position = 0 WHERE id = :id", id=second)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE planning.phases SET position = 1 WHERE id = :id"), {"id": first}
        )
        await conn.execute(
            text("UPDATE planning.phases SET position = 0 WHERE id = :id"), {"id": second}
        )

    async with engine.connect() as conn:
        positions = (await conn.execute(text("SELECT id, position FROM planning.phases"))).all()
    assert {row[0]: row[1] for row in positions} == {first: 1, second: 0}


async def test_one_plan_per_idea_and_spec_version(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada, _, _, plan = await planned(client, engine, app_sessions)

    with pytest.raises(IntegrityError, match="uq_plans_idea_spec_version"):
        await _execute(
            engine,
            "INSERT INTO planning.plans (id, workspace_id, idea_id, spec_version_id) "
            "SELECT :id, workspace_id, idea_id, spec_version_id FROM planning.plans "
            "WHERE id = :plan",
            id=uuid7(),
            plan=plan.id,
        )


async def test_a_ready_plan_needs_a_ready_time(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    _, _, _, plan = await planned(client, engine, app_sessions)

    with pytest.raises(IntegrityError, match="ck_plans_ready_at"):
        await _execute(
            engine, "UPDATE planning.plans SET status = 'ready' WHERE id = :id", id=plan.id
        )
