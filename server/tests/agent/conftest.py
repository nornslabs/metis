"""Fixtures for the LLM gateway tests: Postgres as ``metis_app`` and a fake LLM server.

Set ``TEST_DATABASE_URL`` to a database migrated with ``alembic upgrade head``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
)

from metis.agent.checkpoint import open_checkpointer, setup_checkpointer
from tests.agent.graph_helpers import APP_DATABASE_URL
from tests.agent.llm_helpers import FakeLLMServer
from tests.modules.conftest import app_sessions, engine, redis  # noqa: F401  (shared fixtures)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture
def server() -> FakeLLMServer:
    return FakeLLMServer()


@pytest.fixture
def no_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Error tests should not wait through the provider's retry backoff."""
    monkeypatch.setattr("metis.adapters.llm.chat.MAX_RETRIES", 0)


@pytest_asyncio.fixture
async def checkpointer(engine: AsyncEngine) -> AsyncIterator[AsyncPostgresSaver]:  # noqa: F811
    """A Postgres checkpointer connected as ``metis_app``, like the worker's."""
    await setup_checkpointer(APP_DATABASE_URL)
    async with open_checkpointer(APP_DATABASE_URL) as saver:
        yield saver
