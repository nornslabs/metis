"""LLM Gateway ``llm_enabled`` kill switch tests.

The disabled-flag tests need no database: the gateway raises
``ProviderNotConfiguredError`` before touching the session or the saved key. The enabled
tests exercise the real path against Postgres and a fake LLM server, mirroring
``test_llm_gateway.py``.

``FF_LLM_ENABLED`` drives the :class:`StaticProvider`, so flipping it between
``true``/``false`` flips the kill switch without touching code.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.adapters.flags import StaticProvider
from metis.agent.llm import LLMGateway
from metis.core.config import get_settings
from metis.core.errors import ProviderNotConfiguredError
from metis.helpers.pricing import ModelPrice
from metis.modules.research import EMBEDDING_DIMENSIONS
from tests.agent.llm_helpers import (
    LLM_BASE_URL,
    LLM_KEY,
    FakeLLMServer,
    make_run,
    workspace_with_key,
)


def embeddings_reply(count: int = 2, dimensions: int = EMBEDDING_DIMENSIONS) -> httpx.Response:
    """A minimal OpenAI ``embeddings`` response with ``count`` vectors."""
    data = [
        {"object": "embedding", "index": i, "embedding": [0.01 * (i + 1)] * dimensions}
        for i in range(count)
    ]
    return httpx.Response(
        200,
        json={
            "object": "list",
            "data": data,
            "model": "emb",
            "usage": {"prompt_tokens": 5, "total_tokens": 5},
        },
    )

HELLO = [HumanMessage("hi")]

# Values only need to satisfy ``Settings`` validation (non-empty DB/Redis URLs and a
# 32-byte base64 encryption key); the disabled-flag tests never connect.
_TEST_SETTINGS_ENV = {
    "ENCRYPTION_MASTER_KEY": "lmnZiTdYDe6qnwh5yiWxEBRCzEcA/VCxuwBHAhzWnok=",
    "DATABASE_URL": "postgresql+asyncpg://metis_app:test@localhost:5432/metis",
    "REDIS_URL": "redis://localhost:6379/15",
}


def _settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in _TEST_SETTINGS_ENV.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()


def _gw(
    engine: AsyncEngine,
    workspace_id: UUID,
    sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
    run_id: UUID | None = None,
    prices: dict[str, ModelPrice] | None = None,
) -> LLMGateway:
    return LLMGateway(
        workspace_id,
        run_id or uuid4(),
        sessions=sessions,
        prices=prices or {},
        http_client=server.client(),
        flags=StaticProvider(),
    )


# ------------------------------------------------------------------ disabled flag
async def test_llm_enabled_false_blocks_chat_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_LLM_ENABLED", "false")
    gw = LLMGateway(uuid4(), uuid4(), flags=StaticProvider())

    with pytest.raises(ProviderNotConfiguredError) as caught:
        await gw.chat_model(None, "interview")  # type: ignore[arg-type]

    assert caught.value.meta == {"provider": "llm", "reason": "kill_switch"}


async def test_llm_enabled_false_blocks_embed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_LLM_ENABLED", "false")
    gw = LLMGateway(uuid4(), uuid4(), flags=StaticProvider())

    with pytest.raises(ProviderNotConfiguredError) as caught:
        await gw.embed(None, ["hello"])  # type: ignore[arg-type]

    assert caught.value.meta == {"provider": "llm", "reason": "kill_switch"}


# ------------------------------------------------------------------ enabled flag
async def test_llm_enabled_true_allows_chat_model(
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_LLM_ENABLED", "true")
    get_settings.cache_clear()
    workspace_id = await workspace_with_key(engine)
    run_id = await make_run(engine, workspace_id)
    gw = _gw(engine, workspace_id, app_sessions, server, run_id)

    async with app_sessions() as session:
        model = await gw.chat_model(session, "interview")

    reply = await model.ainvoke(HELLO)
    assert reply.content == "hello"
    assert server.requests[0].headers["authorization"] == f"Bearer {LLM_KEY}"
    assert str(server.requests[0].url) == f"{LLM_BASE_URL}/chat/completions"


async def test_llm_enabled_true_allows_embed(
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_LLM_ENABLED", "true")
    get_settings.cache_clear()
    workspace_id = await workspace_with_key(engine)
    run_id = await make_run(engine, workspace_id)
    gw = _gw(engine, workspace_id, app_sessions, server, run_id)
    server.responder = lambda _request: embeddings_reply(count=2, dimensions=EMBEDDING_DIMENSIONS)

    async with app_sessions() as session:
        vectors = await gw.embed(session, ["one", "two"])

    assert len(vectors) == 2
    assert str(server.requests[0].url) == f"{LLM_BASE_URL}/embeddings"


# -------------------------------------------------- integration via environment var
async def test_ff_llm_enabled_integration_blocks_and_allows(
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """StaticProvider reads ``FF_LLM_ENABLED`` from the environment: off blocks, on allows."""
    _settings_env(monkeypatch)
    workspace_id = await workspace_with_key(engine)
    run_id = await make_run(engine, workspace_id)

    monkeypatch.setenv("FF_LLM_ENABLED", "false")
    get_settings.cache_clear()
    gw_off = _gw(engine, workspace_id, app_sessions, server, run_id)
    async with app_sessions() as session:
        with pytest.raises(ProviderNotConfiguredError):
            await gw_off.chat_model(session, "interview")
    assert server.requests == []

    monkeypatch.setenv("FF_LLM_ENABLED", "true")
    get_settings.cache_clear()
    gw_on = _gw(engine, workspace_id, app_sessions, server, run_id)
    async with app_sessions() as session:
        model = await gw_on.chat_model(session, "interview")
    reply = await model.ainvoke(HELLO)
    assert reply.content == "hello"
    assert len(server.requests) == 1
