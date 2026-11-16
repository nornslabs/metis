"""Migration ``0011_llm_usage``: ``ideas.llm_usage``, its RLS, grants and check constraints.

Seam: what an operator sees in Postgres after ``alembic upgrade head``, plus the downgrade
replayed in a rolled-back transaction (DDL is transactional in Postgres).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.agent.llm_helpers import workspace_without_key
from tests.helpers.auth import APP_ROLE
from tests.helpers.migrations import load_migration

MIGRATION = "0011_llm_usage.py"


async def _scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(text(sql), params)


async def test_the_usage_table_has_forced_row_level_security(engine: AsyncEngine) -> None:
    enabled = await _scalar(
        engine,
        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
        "WHERE oid = 'ideas.llm_usage'::regclass",
    )

    assert enabled is True


@pytest.mark.parametrize("privilege", ["SELECT", "INSERT", "UPDATE", "DELETE"])
async def test_metis_app_can_use_the_usage_table(engine: AsyncEngine, privilege: str) -> None:
    allowed = await _scalar(
        engine,
        "SELECT has_table_privilege(:role, 'ideas.llm_usage', :privilege)",
        role=APP_ROLE,
        privilege=privilege,
    )

    assert allowed is True


async def test_a_run_id_needs_no_runs_table_yet(engine: AsyncEngine) -> None:
    foreign_keys = await _scalar(
        engine,
        "SELECT count(*) FROM pg_constraint "
        "WHERE conrelid = 'ideas.llm_usage'::regclass AND contype = 'f'",
    )

    assert foreign_keys == 1  # the workspace only


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens", "cost_usd"), [(-1, 1, 0), (1, -1, 0), (1, 1, -0.5)]
)
async def test_the_table_refuses_negative_tokens_and_cost(
    engine: AsyncEngine, input_tokens: int, output_tokens: int, cost_usd: float
) -> None:
    workspace_id = await workspace_without_key(engine)

    async with engine.connect() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(
                    "INSERT INTO ideas.llm_usage "
                    "(id, run_id, workspace_id, model, input_tokens, output_tokens, cost_usd) "
                    "VALUES (:id, :run, :ws, 'm', :i, :o, :c)"
                ),
                {
                    "id": uuid4(),
                    "run": uuid4(),
                    "ws": workspace_id,
                    "i": input_tokens,
                    "o": output_tokens,
                    "c": cost_usd,
                },
            )
        await conn.rollback()


async def test_the_downgrade_drops_only_the_usage_table(engine: AsyncEngine) -> None:
    migration = load_migration(MIGRATION)
    assert migration.down_revision == "0010_ideas"

    async with engine.connect() as conn:
        await conn.execute(text("DROP TABLE ideas.llm_usage"))
        assert await conn.scalar(text("SELECT to_regclass('ideas.llm_usage')")) is None
        assert await conn.scalar(text("SELECT to_regclass('ideas.ideas')")) is not None
        await conn.rollback()
