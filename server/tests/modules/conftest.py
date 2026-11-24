"""HTTP-seam fixtures for auth and identity tests: a migrated Postgres, Redis and an app client.

The app's request session runs as the non-superuser ``metis_app`` role
(``SET LOCAL ROLE``), so RLS is enforced exactly as in production. Set
``TEST_DATABASE_URL`` to a database migrated with ``alembic upgrade head``;
tests skip only when Postgres is unreachable or not migrated.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import httpx
import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from metis.core.db import get_request_session, transaction
from metis.core.redis import get_redis
from metis.entrypoints.api import app
from tests.helpers.auth import APP_ROLE, DATABASE_URL, TRUNCATE_USERS

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            ready = await conn.scalar(
                text(
                    "SELECT to_regclass('identity.members') IS NOT NULL "
                    "AND to_regclass('auth.users') IS NOT NULL "
                    "AND to_regclass('auth.sessions') IS NOT NULL "
                    "AND to_regclass('ideas.ideas') IS NOT NULL "
                    "AND to_regclass('ideas.llm_usage') IS NOT NULL "
                    "AND EXISTS (SELECT FROM pg_roles WHERE rolname = :role)"
                ),
                {"role": APP_ROLE},
            )
    except Exception:
        await engine.dispose()
        pytest.skip("Postgres not reachable")
    if not ready:
        await engine.dispose()
        pytest.skip(
            "auth/identity/ideas tables or metis_app role missing; run `alembic upgrade head`"
        )
    async with engine.begin() as conn:
        await conn.execute(text(TRUNCATE_USERS))
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text(TRUNCATE_USERS))
    await engine.dispose()


@pytest_asyncio.fixture
async def app_sessions(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Sessions that run as ``metis_app``, like the api and workers, so RLS applies."""
    app_engine = create_async_engine(DATABASE_URL, poolclass=NullPool)

    @event.listens_for(app_engine.sync_engine, "begin")
    def _as_app_role(conn: object) -> None:
        conn.exec_driver_sql(f"SET LOCAL ROLE {APP_ROLE}")  # type: ignore[attr-defined]

    yield async_sessionmaker(app_engine, expire_on_commit=False)
    await app_engine.dispose()


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[Redis]:
    client: Redis = Redis.from_url(REDIS_URL)
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        pytest.skip("Redis not reachable")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture
async def client(engine: AsyncEngine, redis: Redis) -> AsyncIterator[httpx.AsyncClient]:
    """The app client: request sessions as ``metis_app``, Redis on the test database."""

    async def app_role_session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            async with transaction(session):
                await session.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
                yield session

    app.dependency_overrides[get_request_session] = app_role_session
    app.dependency_overrides[get_redis] = lambda: redis
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def http(client: httpx.AsyncClient) -> httpx.AsyncClient:
    """Alias of ``client`` kept for the session and sign-in tests."""
    return client
