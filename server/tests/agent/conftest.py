"""Fixtures for the LLM gateway tests: Postgres as ``metis_app`` and a fake LLM server.

Set ``TEST_DATABASE_URL`` to a database migrated with ``alembic upgrade head``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from tests.agent.llm_helpers import FakeLLMServer
from tests.helpers.auth import APP_ROLE, DATABASE_URL
from tests.modules.conftest import engine  # noqa: F401  (migrated Postgres fixture)


@pytest.fixture
def server() -> FakeLLMServer:
    return FakeLLMServer()


@pytest.fixture
def no_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Error tests should not wait through the provider's retry backoff."""
    monkeypatch.setattr("metis.adapters.llm.chat.MAX_RETRIES", 0)


@pytest_asyncio.fixture
async def app_sessions(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:  # noqa: F811
    """Sessions that run as ``metis_app``, like the api and workers, so RLS applies."""
    app_engine = create_async_engine(DATABASE_URL, poolclass=NullPool)

    @event.listens_for(app_engine.sync_engine, "begin")
    def _as_app_role(conn: object) -> None:
        conn.exec_driver_sql(f"SET LOCAL ROLE {APP_ROLE}")  # type: ignore[attr-defined]

    yield async_sessionmaker(app_engine, expire_on_commit=False)
    await app_engine.dispose()
