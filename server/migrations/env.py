"""Alembic migration environment.

Prefers the ``DATABASE_URL`` environment variable (set by compose and by local
``.env``) over the value baked into ``alembic.ini``, so migrations work the
same in Docker and on the developer machine regardless of credentials.

When the URL is async (``postgresql+asyncpg``) the online migration runs under
``asyncio`` with an async engine, and the whole configure + run happens inside
``connection.run_sync`` so every DB call stays on the sync greenlet.

Reads DATABASE_URL from settings via get_settings() for a single source of truth.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_database_url() -> str:
    """Resolve DATABASE_URL from environment or alembic.ini.

    Prefers DATABASE_URL from the pydantic Settings system for consistency
    with the application, but falls back to the raw environment variable
    for migration operations that may run before all settings are configured.
    """
    # Try pydantic Settings first (single source of truth)
    try:
        from metis.core.config import get_settings

        return get_settings().database_url
    except Exception:
        # Fallback to environment variable for migration-only runs
        url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
        if url is None:
            raise RuntimeError(
                "DATABASE_URL is not set and sqlalchemy.url is not configured in alembic.ini"
            ) from None
        return url


database_url = _resolve_database_url()
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    In this mode, the Context is given a URL
    directly, and no Engine is created.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=None, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _do_migrations(sync_conn: Connection) -> None:
    """Run migrations using the sync connection from async context."""
    context.configure(connection=sync_conn, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario, we create an Engine and
    associate a connection with the Context.
    """
    if "+asyncpg" in database_url:
        async_engine = create_async_engine(
            database_url,
            poolclass=pool.AsyncAdaptedQueuePool,
        )

        async def _run_async() -> None:
            async with async_engine.connect() as connection:
                await connection.run_sync(_do_migrations)

        asyncio.run(_run_async())
    else:
        # Non-async URL (postgres://) - rarely used but supported
        from sqlalchemy import engine_from_config

        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as conn:
            _do_migrations(conn)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()