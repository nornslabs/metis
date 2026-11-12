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
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# Import settings to resolve DATABASE_URL from env (single source of truth)
from metis.core.config import get_settings


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _get_database_url() -> str:
    """Resolve DATABASE_URL from pydantic Settings.

    This makes the migration environment read from the same settings
    source as the application, ensuring consistency.
    """
    settings = get_settings()
    return settings.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    In this mode, the Context is given a URL
    directly, and no Engine is created.
    """
    url = _get_database_url()
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
    database_url = _get_database_url()

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
        connectable = context.engine_from_config(
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