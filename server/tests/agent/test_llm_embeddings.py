"""LLM gateway embedding tests.

Seam: ``LLMGateway.embed`` against real Postgres (as ``metis_app``, RLS on) and a fake
OpenAI-compatible server behind ``httpx.MockTransport``. Assertions cover what a caller
sees: the vectors (or ``None``), the raised error, the request sent and the usage rows.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.llm import LLMGateway
from metis.core.config import get_settings
from metis.core.errors import ProviderNotConfiguredError, UpstreamError
from metis.helpers.http import FailureReason
from metis.modules.research import EMBEDDING_DIMENSIONS
from tests.agent.llm_helpers import (
    LLM_BASE_URL,
    LLM_KEY,
    FakeLLMServer,
    make_run,
    usage_rows,
    workspace_with_key,
    workspace_without_key,
)

if TYPE_CHECKING:
    from uuid import UUID

Sessions = async_sessionmaker[AsyncSession]


def embeddings_reply(
    count: int = 1, dimensions: int = EMBEDDING_DIMENSIONS, prompt_tokens: int = 5
) -> httpx.Response:
    """A minimal OpenAI ``embeddings`` response with ``count`` vectors."""
    data = [
        {"object": "embedding", "index": i, "embedding": [0.01 * (i + 1)] * dimensions}
        for i in range(count)
    ]
    usage = {"prompt_tokens": prompt_tokens, "total_tokens": prompt_tokens}
    return httpx.Response(
        200, json={"object": "list", "data": data, "model": "emb", "usage": usage}
    )


async def _gateway(
    engine: AsyncEngine, workspace_id: UUID, sessions: Sessions, server: FakeLLMServer
) -> LLMGateway:
    run_id = await make_run(engine, workspace_id)
    return LLMGateway(
        workspace_id, run_id, sessions=sessions, prices={}, http_client=server.client()
    )


async def _embed(gw: LLMGateway, sessions: Sessions, *texts: str) -> list[list[float]] | None:
    async with sessions() as session:
        return await gw.embed(session, list(texts))


async def test_embed_returns_one_vector_per_text_and_records_usage(
    engine: AsyncEngine, app_sessions: Sessions, server: FakeLLMServer
) -> None:
    workspace_id = await workspace_with_key(engine)
    server.responder = lambda _request: embeddings_reply(count=2, prompt_tokens=9)
    gw = await _gateway(engine, workspace_id, app_sessions, server)

    vectors = await _embed(gw, app_sessions, "Acme CRM", "Bolt")

    assert vectors is not None
    assert [len(v) for v in vectors] == [EMBEDDING_DIMENSIONS, EMBEDDING_DIMENSIONS]
    assert vectors[1][0] == pytest.approx(0.02)
    request = server.requests[0]
    assert str(request.url) == f"{LLM_BASE_URL}/embeddings"
    assert request.headers["authorization"] == f"Bearer {LLM_KEY}"
    body = json.loads(request.read())
    model = get_settings().llm_embedding_model
    assert (body["model"], body["input"], body["encoding_format"]) == (
        model,
        ["Acme CRM", "Bolt"],
        "float",
    )
    [row] = await usage_rows(engine, workspace_id)
    assert (row.model, row.input_tokens, row.output_tokens) == (model, 9, 0)


async def test_embedding_nothing_makes_no_call(
    engine: AsyncEngine, app_sessions: Sessions, server: FakeLLMServer
) -> None:
    workspace_id = await workspace_with_key(engine)
    gw = await _gateway(engine, workspace_id, app_sessions, server)

    assert await _embed(gw, app_sessions) == []
    assert server.requests == []


@pytest.mark.usefixtures("no_retries")
async def test_a_provider_without_embeddings_gives_none_once_and_is_not_asked_again(
    engine: AsyncEngine,
    app_sessions: Sessions,
    server: FakeLLMServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    workspace_id = await workspace_with_key(engine)
    server.responder = lambda _request: httpx.Response(404, json={"error": {"message": "no"}})
    gw = await _gateway(engine, workspace_id, app_sessions, server)

    assert await _embed(gw, app_sessions, "Acme") is None
    assert await _embed(gw, app_sessions, "Bolt") is None

    assert len(server.requests) == 1
    assert "llm.embeddings_unavailable" in caplog.text
    assert await usage_rows(engine, workspace_id) == []


async def test_vectors_of_the_wrong_size_give_none(
    engine: AsyncEngine, app_sessions: Sessions, server: FakeLLMServer
) -> None:
    workspace_id = await workspace_with_key(engine)
    server.responder = lambda _request: embeddings_reply(dimensions=768)
    gw = await _gateway(engine, workspace_id, app_sessions, server)

    assert await _embed(gw, app_sessions, "Acme") is None
    assert await _embed(gw, app_sessions, "Bolt") is None
    assert len(server.requests) == 1


@pytest.mark.usefixtures("no_retries")
async def test_other_provider_errors_are_raised_as_safe_upstream_errors(
    engine: AsyncEngine, app_sessions: Sessions, server: FakeLLMServer
) -> None:
    workspace_id = await workspace_with_key(engine)
    server.responder = lambda _request: httpx.Response(401, json={"error": f"bad {LLM_KEY}"})
    gw = await _gateway(engine, workspace_id, app_sessions, server)

    with pytest.raises(UpstreamError) as caught:
        await _embed(gw, app_sessions, "Acme")

    assert caught.value.meta == {"provider": "llm", "reason": FailureReason.UNAUTHORIZED.value}
    assert LLM_KEY not in str(caught.value)


async def test_a_workspace_without_a_key_cannot_embed(
    engine: AsyncEngine, app_sessions: Sessions, server: FakeLLMServer
) -> None:
    workspace_id = await workspace_without_key(engine)
    gw = await _gateway(engine, workspace_id, app_sessions, server)

    with pytest.raises(ProviderNotConfiguredError):
        await _embed(gw, app_sessions, "Acme")
    assert server.requests == []


async def test_closing_the_gateway_closes_the_embedder(
    engine: AsyncEngine, app_sessions: Sessions, server: FakeLLMServer
) -> None:
    workspace_id = await workspace_with_key(engine)
    server.responder = lambda _request: embeddings_reply()
    http = server.client()
    gw = LLMGateway(
        workspace_id,
        await make_run(engine, workspace_id),
        sessions=app_sessions,
        prices={},
        http_client=http,
    )
    await _embed(gw, app_sessions, "Acme")

    await gw.aclose()

    assert http.is_closed
