"""LLM gateway tests.

Seam: ``LLMGateway`` against real Postgres (sessions as ``metis_app``, RLS on) and a
fake OpenAI-compatible server behind ``httpx.MockTransport``. Nothing leaves the process.
Assertions are limited to what a caller sees: the reply, the raised error, the request the
server received and the stored usage rows.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx
import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.llm import LLMGateway
from metis.core.errors import ProviderNotConfiguredError, UpstreamError
from metis.core.ports import LLMProvider
from metis.helpers.http import FailureReason
from metis.helpers.ids import uuid7
from metis.helpers.pricing import ModelPrice
from tests.agent.llm_helpers import (
    LLM_BASE_URL,
    LLM_KEY,
    LLM_MODEL,
    FakeLLMServer,
    chat_completion,
    make_run,
    usage_rows,
    workspace_with_key,
    workspace_without_key,
)

if TYPE_CHECKING:
    from uuid import UUID

HELLO = [HumanMessage("hi")]


async def gateway(
    engine: AsyncEngine,
    workspace_id: UUID,
    sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
    run_id: UUID | None = None,
    prices: dict[str, ModelPrice] | None = None,
) -> LLMGateway:
    return LLMGateway(
        workspace_id,
        run_id or await make_run(engine, workspace_id),
        sessions=sessions,
        prices=prices or {},
        http_client=server.client(),
    )


async def model_for(
    gw: LLMGateway, sessions: async_sessionmaker[AsyncSession], purpose: str = "interview"
) -> LLMProvider:
    async with sessions() as session:
        return await gw.chat_model(session, purpose)


async def failure_reason(model: LLMProvider) -> str:
    with pytest.raises(UpstreamError) as caught:
        await model.ainvoke(HELLO)
    assert caught.value.meta == {"provider": "llm", "reason": caught.value.meta["reason"]}
    assert LLM_KEY not in str(caught.value)
    return str(caught.value.meta["reason"])


# ------------------------------------------------------------------ happy path
async def test_a_saved_key_gives_a_working_chat_model_that_records_usage(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], server: FakeLLMServer
) -> None:
    workspace_id = await workspace_with_key(engine)
    run_id = await make_run(engine, workspace_id)
    gw = await gateway(engine, workspace_id, app_sessions, server, run_id)

    reply = await (await model_for(gw, app_sessions)).ainvoke(HELLO)

    request = server.requests[0]
    assert reply.content == "hello"
    assert str(request.url) == f"{LLM_BASE_URL}/chat/completions"
    assert request.headers["authorization"] == f"Bearer {LLM_KEY}"
    assert request.read().decode().count(f'"model":"{LLM_MODEL}"') == 1
    rows = await usage_rows(engine, workspace_id)
    assert [(r.run_id, r.model, r.input_tokens, r.output_tokens) for r in rows] == [
        (run_id, LLM_MODEL, 11, 7)
    ]


async def test_missing_usage_in_the_reply_records_zero_tokens_and_no_cost(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], server: FakeLLMServer
) -> None:
    workspace_id = await workspace_with_key(engine)
    server.responder = lambda _request: chat_completion(usage=None)
    gw = await gateway(engine, workspace_id, app_sessions, server)

    await (await model_for(gw, app_sessions)).ainvoke(HELLO)

    [row] = await usage_rows(engine, workspace_id)
    assert (row.input_tokens, row.output_tokens, row.cost_usd) == (0, 0, None)


async def test_a_configured_price_fills_in_the_cost_and_an_unpriced_model_has_none(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], server: FakeLLMServer
) -> None:
    priced = await workspace_with_key(engine, "priced", model="priced-model")
    unpriced = await workspace_with_key(engine, "unpriced", model="other-model")
    price = ModelPrice(input_per_million_usd=Decimal(2), output_per_million_usd=Decimal(10))
    prices = {"priced-model": price}

    for workspace_id in (priced, unpriced):
        gw = await gateway(engine, workspace_id, app_sessions, server, prices=prices)
        await (await model_for(gw, app_sessions)).ainvoke(HELLO)

    # 11 * 2 / 1e6 + 7 * 10 / 1e6
    assert (await usage_rows(engine, priced))[0].cost_usd == Decimal("0.000092")
    assert (await usage_rows(engine, unpriced))[0].cost_usd is None


async def test_every_call_of_a_run_adds_a_usage_row(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], server: FakeLLMServer
) -> None:
    workspace_id = await workspace_with_key(engine)
    gw = await gateway(engine, workspace_id, app_sessions, server)
    model = await model_for(gw, app_sessions)

    await model.ainvoke(HELLO)
    await model.ainvoke(HELLO)

    assert len(await usage_rows(engine, workspace_id)) == 2


async def test_the_same_purpose_reuses_the_model_and_purpose_sets_the_temperature(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], server: FakeLLMServer
) -> None:
    workspace_id = await workspace_with_key(engine)
    gw = await gateway(engine, workspace_id, app_sessions, server)

    first = await model_for(gw, app_sessions, "score")
    again = await model_for(gw, app_sessions, "score")
    chatty = await model_for(gw, app_sessions, "interview")
    await first.ainvoke(HELLO)
    await chatty.ainvoke(HELLO)

    assert first is again
    assert first is not chatty
    assert '"temperature":0.0' in server.requests[0].read().decode()
    assert '"temperature":0.7' in server.requests[1].read().decode()


# ------------------------------------------------------------- credentials
async def test_a_workspace_without_a_key_gets_provider_not_configured_and_no_call(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], server: FakeLLMServer
) -> None:
    workspace_id = await workspace_without_key(engine)
    gw = await gateway(engine, workspace_id, app_sessions, server)

    with pytest.raises(ProviderNotConfiguredError):
        await model_for(gw, app_sessions)

    assert server.requests == []


async def test_a_workspace_uses_only_its_own_key_and_usage_stays_in_its_workspace(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], server: FakeLLMServer
) -> None:
    mine = await workspace_with_key(engine, "mine", key="sk-mine-0123456789")
    theirs = await workspace_with_key(engine, "theirs", key="sk-theirs-0123456789")

    gw = await gateway(engine, mine, app_sessions, server)
    await (await model_for(gw, app_sessions)).ainvoke(HELLO)

    assert server.requests[0].headers["authorization"] == "Bearer sk-mine-0123456789"
    assert len(await usage_rows(engine, mine)) == 1
    assert await usage_rows(engine, theirs) == []


async def test_usage_is_invisible_across_workspaces_under_rls(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], server: FakeLLMServer
) -> None:
    from sqlalchemy import text

    mine = await workspace_with_key(engine, "mine")
    other = await workspace_with_key(engine, "other")
    await (
        await model_for(await gateway(engine, mine, app_sessions, server), app_sessions)
    ).ainvoke(HELLO)

    async with app_sessions() as session:
        await session.execute(
            text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": str(other)}
        )
        visible = await session.scalar(text("SELECT count(*) FROM ideas.llm_usage"))

    assert visible == 0


# ------------------------------------------------------------------ failures
@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (401, FailureReason.UNAUTHORIZED),
        (403, FailureReason.UNAUTHORIZED),
        (429, FailureReason.RATE_LIMITED),
        (500, FailureReason.SERVER_ERROR),
        (400, FailureReason.BAD_RESPONSE),
    ],
)
@pytest.mark.usefixtures("no_retries")
async def test_an_error_status_becomes_a_safe_upstream_error(
    status: int,
    reason: FailureReason,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
) -> None:
    workspace_id = await workspace_with_key(engine)
    server.responder = lambda _request: httpx.Response(
        status, json={"error": {"message": f"upstream said {LLM_KEY}"}}
    )
    model = await model_for(await gateway(engine, workspace_id, app_sessions, server), app_sessions)

    assert await failure_reason(model) == reason.value
    assert await usage_rows(engine, workspace_id) == []


@pytest.mark.usefixtures("no_retries")
async def test_a_malformed_reply_is_a_bad_response(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], server: FakeLLMServer
) -> None:
    workspace_id = await workspace_with_key(engine)
    server.responder = lambda _request: httpx.Response(200, text="<html>not json</html>")
    model = await model_for(await gateway(engine, workspace_id, app_sessions, server), app_sessions)

    assert await failure_reason(model) == FailureReason.BAD_RESPONSE.value


@pytest.mark.usefixtures("no_retries")
async def test_an_unreachable_endpoint_is_unreachable(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], server: FakeLLMServer
) -> None:
    workspace_id = await workspace_with_key(engine)

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    server.responder = refuse
    model = await model_for(await gateway(engine, workspace_id, app_sessions, server), app_sessions)

    assert await failure_reason(model) == FailureReason.UNREACHABLE.value


@pytest.mark.usefixtures("no_retries")
async def test_a_stalled_endpoint_is_a_timeout(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], server: FakeLLMServer
) -> None:
    workspace_id = await workspace_with_key(engine)

    def stall(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    server.responder = stall
    model = await model_for(await gateway(engine, workspace_id, app_sessions, server), app_sessions)

    assert await failure_reason(model) == FailureReason.TIMEOUT.value


async def test_a_transient_server_error_is_retried(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], server: FakeLLMServer
) -> None:
    workspace_id = await workspace_with_key(engine)
    replies = iter([httpx.Response(500, json={"error": {"message": "boom"}}), chat_completion()])
    server.responder = lambda _request: next(replies)
    model = await model_for(await gateway(engine, workspace_id, app_sessions, server), app_sessions)

    reply = await model.ainvoke(HELLO)

    assert reply.content == "hello"
    assert len(server.requests) == 2
    assert len(await usage_rows(engine, workspace_id)) == 1


@pytest.mark.usefixtures("no_retries")
async def test_a_failing_call_keeps_the_usage_of_earlier_calls_and_logs_no_secret(
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    workspace_id = await workspace_with_key(engine)
    model = await model_for(await gateway(engine, workspace_id, app_sessions, server), app_sessions)
    await model.ainvoke(HELLO)
    server.responder = lambda _request: httpx.Response(401, json={"error": f"bad {LLM_KEY}"})

    await failure_reason(model)

    assert len(await usage_rows(engine, workspace_id)) == 1
    assert LLM_KEY not in caplog.text


# ---------------------------------------------------------------------- close
async def test_closing_the_gateway_closes_its_models_and_allows_a_new_one(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], server: FakeLLMServer
) -> None:
    workspace_id = await workspace_with_key(engine)
    http = server.client()
    gw = LLMGateway(workspace_id, uuid7(), sessions=app_sessions, prices={}, http_client=http)
    await model_for(gw, app_sessions)

    await gw.aclose()

    assert http.is_closed
