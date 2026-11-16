"""The agent worker creates the graph's checkpoint tables when it starts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.entrypoints.worker import AgentWorkerSettings, MaintenanceWorkerSettings
from tests.modules.conftest import engine  # noqa: F401  (migrated Postgres fixture)


async def test_agent_worker_startup_creates_the_checkpoint_tables(
    engine: AsyncEngine,  # noqa: F811
) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA agent CASCADE"))
        await conn.execute(text("CREATE SCHEMA agent"))
        await conn.execute(text("GRANT USAGE, CREATE ON SCHEMA agent TO metis_app"))
        await conn.execute(
            text("ALTER DEFAULT PRIVILEGES IN SCHEMA agent GRANT ALL ON TABLES TO metis_app")
        )
    ctx: dict[str, Any] = {}

    await AgentWorkerSettings.on_startup(ctx)
    try:
        async with engine.connect() as conn:
            tables = {
                row[0]
                for row in await conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'agent'")
                )
            }
    finally:
        await AgentWorkerSettings.on_shutdown(ctx)

    assert "checkpoints" in tables


def test_maintenance_worker_does_not_touch_the_checkpointer() -> None:
    assert MaintenanceWorkerSettings.on_startup is not AgentWorkerSettings.on_startup
