"""Alembic migration environment.

Prefers the ``DATABASE_URL`` environment variable (set by compose and by local
``.env``) over the value baked into ``alembic.ini``, so migrations work the
same in Docker and on the developer machine regardless of credentials.

When the URL is async (``postgresql+asyncpg``) the online migration runs under
``asyncio`` with an async engine, and the whole configure + run happens inside
``connection.run_sync`` so every DB call stays on the sync greenlet.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=None, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _do_migrations(sync_conn) -> None:
    context.configure(connection=sync_conn, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if "+asyncpg" in url:
        from sqlalchemy.ext.asyncio import create_async_engine

        connectable = create_async_engine(url, poolclass=pool.AsyncAdaptedQueuePool)

        async def _run() -> None:
            async with connectable.connect() as connection:
                await connection.run_sync(_do_migrations)

        asyncio.run(_run())
    else:
        from sqlalchemy import engine_from_config

        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            _do_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
