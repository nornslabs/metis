"""The graph's Postgres checkpointer.

LangGraph's ``AsyncPostgresSaver`` stores one checkpoint thread per run (``thread_id`` is
the run id), so a paused run resumes from a fresh graph in any process. It talks to
Postgres through ``psycopg``, with its own small pool on the app's ``DATABASE_URL``
(search path set to ``agent``). Its tables live in the ``agent`` schema (migration
``0012_agent_checkpoints``), which ``metis_app`` may create tables in; ``setup()`` creates them.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.engine import make_url

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

CHECKPOINT_SCHEMA = "agent"
POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 5


def psycopg_conninfo(database_url: str) -> str:
    """A libpq URL from the app's SQLAlchemy URL."""
    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


@asynccontextmanager
async def open_checkpointer(database_url: str) -> AsyncGenerator[AsyncPostgresSaver]:
    """A saver on its own connection pool; the pool closes when the block ends."""
    conninfo = psycopg_conninfo(database_url)
    connection_kwargs: dict[str, Any] = {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
        "options": f"-c search_path={CHECKPOINT_SCHEMA}",
    }
    async with AsyncConnectionPool(
        conninfo,
        min_size=POOL_MIN_SIZE,
        max_size=POOL_MAX_SIZE,
        kwargs=connection_kwargs,
        open=False,
    ) as pool:
        yield AsyncPostgresSaver(pool)  # type: ignore[arg-type]


async def setup_checkpointer(database_url: str) -> None:
    """Create or migrate the checkpoint tables. Idempotent; run at worker start."""
    async with open_checkpointer(database_url) as saver:
        await saver.setup()
