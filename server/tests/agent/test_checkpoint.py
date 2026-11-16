"""The checkpointer connects as ``metis_app``, creates its tables in ``agent`` and is idempotent."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.agent.checkpoint import open_checkpointer, setup_checkpointer
from tests.helpers.auth import DATABASE_URL
from tests.modules.conftest import engine  # noqa: F401  (migrated Postgres fixture)

APP_URL = make_url(DATABASE_URL).set(username="metis_app", password="metis_app")


async def _agent_tables(engine: AsyncEngine) -> set[str]:  # noqa: F811
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'agent'")
        )
        return {row[0] for row in rows}


async def test_setup_as_app_role_creates_checkpoint_tables_in_agent_schema(
    engine: AsyncEngine,  # noqa: F811
) -> None:
    url = APP_URL.render_as_string(hide_password=False)

    await setup_checkpointer(url)
    await setup_checkpointer(url)

    assert {"checkpoints", "checkpoint_writes", "checkpoint_blobs"} <= await _agent_tables(engine)


async def test_open_checkpointer_gives_a_usable_saver(
    engine: AsyncEngine,  # noqa: F811
) -> None:
    url = APP_URL.render_as_string(hide_password=False)
    await setup_checkpointer(url)

    async with open_checkpointer(url) as saver:
        assert await saver.aget_tuple({"configurable": {"thread_id": "none"}}) is None
