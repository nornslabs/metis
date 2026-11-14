"""HTTP-seam fixtures for identity tests: a migrated Postgres and an app client.

The app's request session runs as the non-superuser ``metis_app`` role
(``SET LOCAL ROLE``), so RLS is enforced exactly as in production. Set
``TEST_DATABASE_URL`` to a database migrated with ``alembic upgrade head``;
tests skip only when Postgres is unreachable or not migrated.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from api_helpers import APP_ROLE, DATABASE_URL, TRUNCATE_IDENTITY
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from metis.core.db import get_request_session, transaction
from metis.core.redis import get_redis
from metis.entrypoints.api import app

REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            ready = await conn.scalar(
                text(
                    "SELECT to_regclass('identity.members') IS NOT NULL "
                    "AND EXISTS (SELECT FROM pg_roles WHERE rolname = :role)"
                ),
                {"role": APP_ROLE},
            )
    except Exception:  # noqa: BLE001
        await engine.dispose()
        pytest.skip("Postgres not reachable")
    if not ready:
        await engine.dispose()
        pytest.skip("identity tables or metis_app role missing; run `alembic upgrade head`")
    async with engine.begin() as conn:
        await conn.execute(text(TRUNCATE_IDENTITY))
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text(TRUNCATE_IDENTITY))
    await engine.dispose()


@pytest_asyncio.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    async def app_role_session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            async with transaction(session):
                await session.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
                yield session

    app.dependency_overrides[get_request_session] = app_role_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[Redis]:
    client: Redis = Redis.from_url(REDIS_URL)
    try:
        await client.ping()
    except Exception:  # noqa: BLE001
        await client.aclose()
        pytest.skip("Redis not reachable")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture
async def http(client: httpx.AsyncClient, redis: Redis) -> httpx.AsyncClient:
    """The app client with the request Redis pointed at the test database."""
    app.dependency_overrides[get_redis] = lambda: redis
    return client
