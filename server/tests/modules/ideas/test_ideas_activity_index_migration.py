"""Migration ``0022_ideas_activity_index``: the list-by-last-activity index exists in Postgres."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.helpers.migrations import load_migration

MIGRATION = load_migration("0022_ideas_activity_index.py")


async def test_the_index_orders_live_ideas_of_a_workspace_by_last_activity(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as conn:
        definition = await conn.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
            {"name": MIGRATION.INDEX},
        )

    assert definition is not None
    assert "(workspace_id, updated_at DESC, id DESC)" in definition
    assert "archived_at IS NULL" in definition
