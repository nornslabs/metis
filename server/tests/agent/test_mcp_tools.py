"""Linear tools in the agent graph (SHIP-233).

Seam: the tools a specialist gets from ``load_mcp_tools``, called as the tool loop would, on
real Postgres as ``metis_app`` and real Redis, with Linear's OAuth and MCP servers faked
in-process (``tests/helpers/fake_linear.py``). Tests check what a specialist sees (tool names,
results, refusals), what the run's event stream shows and what is stored (connection status),
never internals.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from langchain_core.tools import BaseTool
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.tools.mcp import (
    MAX_RESULT_CHARS,
    UNAVAILABLE_TEXT,
    McpRunContext,
    load_mcp_tools,
    load_optional_mcp_tools,
    summarize_args,
)
from metis.agent.tools.mcp_policy import (
    INTEGRATOR_POLICY,
    PLANNER_POLICY,
    ApprovalLedger,
    McpToolPolicy,
    McpWriteRefused,
)
from metis.core.errors import (
    IntegrationExpiredError,
    IntegrationNotConnectedError,
    UpstreamError,
)
from metis.core.events import RunEvent, RunEventType, read
from tests.agent.linear_helpers import connect_workspace, connection_status, run_context
from tests.agent.llm_helpers import workspace_without_key
from tests.helpers.fake_linear import BIG_RESULT_CHARS, FakeLinear

ALL_TOOLS = (
    "list_teams",
    "list_projects",
    "list_issues",
    "list_issue_labels",
    "save_project",
    "save_milestone",
    "save_issue",
    "delete_issue",
    "big_result",
)
APPROVED = {"action": "Export the plan to Linear", "details": "3 issues", "approved": True}


@pytest_asyncio.fixture
async def linear() -> AsyncIterator[FakeLinear]:
    async with FakeLinear(tools=ALL_TOOLS).running() as fake:
        yield fake


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("metis.agent.tools.mcp.RETRY_DELAY_SECONDS", 0)


class Setup:
    def __init__(self, workspace_id: UUID, context: McpRunContext) -> None:
        self.workspace_id = workspace_id
        self.context = context

    async def events(self, redis: Redis) -> list[RunEvent]:
        return [e async for e in read(str(self.context.run_id), redis=redis)]


async def _setup(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    redis: Redis,
    linear: FakeLinear,
    *,
    connect: bool = True,
    status: str = "connected",
) -> Setup:
    workspace_id = await workspace_without_key(engine)
    if connect:
        await connect_workspace(engine, sessions, workspace_id, linear, status=status)
    context = run_context(redis, sessions, workspace_id, uuid4(), linear)
    return Setup(workspace_id, context)


def _names(tools: list[BaseTool]) -> set[str]:
    return {tool.name for tool in tools}


def _tool(tools: list[BaseTool], name: str) -> BaseTool:
    return next(tool for tool in tools if tool.name == name)


# ------------------------------------------------------------------ allow-list
async def test_the_planner_sees_only_its_three_read_tools(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)

    tools = await load_mcp_tools(setup.context, PLANNER_POLICY)

    assert _names(tools) == {"list_teams", "list_projects", "list_issues"}


async def test_the_integrator_sees_its_two_read_tools_and_three_write_tools(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)

    tools = await load_mcp_tools(setup.context, INTEGRATOR_POLICY)

    assert _names(tools) == {
        "list_teams",
        "list_issue_labels",
        "save_project",
        "save_milestone",
        "save_issue",
    }


async def test_a_policy_with_no_tools_loads_nothing_and_never_calls_linear(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear, connect=False)

    assert await load_mcp_tools(setup.context, McpToolPolicy()) == []


async def test_a_listed_tool_the_server_lacks_is_left_out(
    engine: AsyncEngine, app_sessions: Any, redis: Redis
) -> None:
    async with FakeLinear(tools=("list_teams", "list_issues")).running() as linear:
        setup = await _setup(engine, app_sessions, redis, linear)

        tools = await load_mcp_tools(setup.context, PLANNER_POLICY)

    assert _names(tools) == {"list_teams", "list_issues"}


# ----------------------------------------------------------------- write gate
async def test_a_write_without_approval_is_refused_and_never_reaches_linear(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, INTEGRATOR_POLICY, ApprovalLedger())

    with pytest.raises(McpWriteRefused):
        await _tool(tools, "save_issue").ainvoke({"title": "Ship it"})

    assert linear.tool_calls == []
    assert [e for e in await setup.events(redis) if e.type is RunEventType.TOOL_CALL] == []


async def test_a_denied_approval_records_nothing_so_the_write_is_still_refused(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    denied = ApprovalLedger({"action": "x", "details": "y", "approved": False})
    tools = await load_mcp_tools(setup.context, INTEGRATOR_POLICY, denied)

    with pytest.raises(McpWriteRefused):
        await _tool(tools, "save_issue").ainvoke({"title": "Ship it"})

    assert linear.tool_calls == []


async def test_an_approved_write_reaches_linear_and_shows_as_a_write_event(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    ledger = ApprovalLedger(APPROVED)
    tools = await load_mcp_tools(setup.context, INTEGRATOR_POLICY, ledger)

    result = await _tool(tools, "save_issue").ainvoke({"title": "Ship it"})

    assert result == "save_issue"
    assert linear.tool_calls == [("save_issue", {"query": "", "title": "Ship it"})]
    (event,) = [e for e in await setup.events(redis) if e.type is RunEventType.TOOL_CALL]
    assert event.data == {
        "provider": "linear",
        "name": "save_issue",
        "summary": "title: Ship it",
        "kind": "write",
    }


async def test_granting_approval_during_the_visit_unlocks_the_writes(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    ledger = ApprovalLedger()
    tools = await load_mcp_tools(setup.context, INTEGRATOR_POLICY, ledger)

    ledger.grant("Export the plan", "3 issues")
    await _tool(tools, "save_issue").ainvoke({"title": "Ship it"})

    assert ledger.record == {"action": "Export the plan", "details": "3 issues", "approved": True}
    assert len(linear.tool_calls) == 1


async def test_a_read_needs_no_approval(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, PLANNER_POLICY)

    result = await _tool(tools, "list_issues").ainvoke({"query": "billing"})

    assert result == "list_issues"
    (event,) = [e for e in await setup.events(redis) if e.type is RunEventType.TOOL_CALL]
    assert event.data["kind"] == "read"
    assert event.data["summary"] == "query: billing"


# ------------------------------------------------------------- events, results
async def test_the_event_summary_is_short_and_carries_no_token(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, PLANNER_POLICY)

    await _tool(tools, "list_issues").ainvoke({"query": "q" * 500})

    (event,) = [e for e in await setup.events(redis) if e.type is RunEventType.TOOL_CALL]
    assert len(event.data["summary"]) <= 120
    assert not any(token in str(event.data) for token in linear.mcp_tokens_seen if token)


def test_summary_falls_back_to_argument_names() -> None:
    assert summarize_args({"b": 1, "a": 2}) == "args: a, b"
    assert summarize_args({}) == "no arguments"


async def test_a_long_result_is_cut_before_it_reaches_the_model(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, McpToolPolicy(read=frozenset({"big_result"})))

    result = await _tool(tools, "big_result").ainvoke({})

    assert result.startswith("x" * MAX_RESULT_CHARS)
    assert result.endswith(f"[truncated {BIG_RESULT_CHARS - MAX_RESULT_CHARS} characters]")


async def test_a_short_result_is_untouched(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, PLANNER_POLICY)

    assert await _tool(tools, "list_projects").ainvoke({}) == "list_projects"


# ---------------------------------------------------------------- failures
async def test_a_read_is_retried_once_after_a_transient_failure(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, PLANNER_POLICY)
    linear.transient_failures = 1

    result = await _tool(tools, "list_issues").ainvoke({"query": "billing"})

    assert result == "list_issues"
    assert len(linear.tool_calls) == 1


async def test_a_write_is_never_retried_after_a_transient_failure(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, INTEGRATOR_POLICY, ApprovalLedger(APPROVED))
    linear.transient_failures = 1

    with pytest.raises(UpstreamError) as raised:
        await _tool(tools, "save_issue").ainvoke({"title": "Ship it"})

    assert raised.value.meta == {"provider": "linear", "reason": "server_error"}
    assert linear.tool_calls == []
    assert await connection_status(engine, setup.workspace_id) == "connected"


async def test_a_provider_outage_is_not_read_as_an_expired_connection(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, PLANNER_POLICY)
    linear.transient_failures = 5

    with pytest.raises(UpstreamError):
        await _tool(tools, "list_issues").ainvoke({})

    assert await connection_status(engine, setup.workspace_id) == "connected"


async def test_a_rejected_token_on_a_read_is_refreshed_and_the_read_retried(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, PLANNER_POLICY)
    linear.revoke_access_tokens()

    result = await _tool(tools, "list_issues").ainvoke({"query": "billing"})

    assert result == "list_issues"
    assert linear.refresh_count == 1


async def test_a_failed_call_still_publishes_its_event(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, PLANNER_POLICY)
    linear.transient_failures = 5

    with pytest.raises(UpstreamError):
        await _tool(tools, "list_issues").ainvoke({"query": "billing"})

    events = [e for e in await setup.events(redis) if e.type is RunEventType.TOOL_CALL]
    assert [e.data["name"] for e in events] == ["list_issues"]


async def test_a_rejected_token_is_refreshed_once_and_the_call_goes_through(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, INTEGRATOR_POLICY, ApprovalLedger(APPROVED))
    linear.revoke_access_tokens()

    result = await _tool(tools, "save_issue").ainvoke({"title": "Ship it"})

    assert result == "save_issue"
    assert linear.refresh_count == 1
    assert linear.tool_calls == [("save_issue", {"query": "", "title": "Ship it"})]
    assert await connection_status(engine, setup.workspace_id) == "connected"


async def test_a_refresh_the_provider_rejects_expires_the_connection_and_fails_the_step(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, INTEGRATOR_POLICY, ApprovalLedger(APPROVED))
    linear.revoke_access_tokens()
    linear.refresh_status = 400

    with pytest.raises(IntegrationExpiredError) as raised:
        await _tool(tools, "save_issue").ainvoke({"title": "Ship it"})

    assert raised.value.meta == {"provider": "linear"}
    assert await connection_status(engine, setup.workspace_id) == "expired"
    assert linear.tool_calls == []


async def test_a_second_rejection_after_a_refresh_expires_the_connection(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, INTEGRATOR_POLICY, ApprovalLedger(APPROVED))
    linear.mcp_unauthorized = True

    with pytest.raises(IntegrationExpiredError):
        await _tool(tools, "save_issue").ainvoke({"title": "Ship it"})

    assert await connection_status(engine, setup.workspace_id) == "expired"


async def test_the_planner_goes_on_without_linear_when_the_connection_lapses_mid_step(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, PLANNER_POLICY)
    linear.mcp_unauthorized = True

    first = await _tool(tools, "list_issues").ainvoke({})
    second = await _tool(tools, "list_teams").ainvoke({})

    assert (first, second) == (UNAVAILABLE_TEXT, UNAVAILABLE_TEXT)
    assert await connection_status(engine, setup.workspace_id) == "expired"
    notices = [e for e in await setup.events(redis) if e.type is RunEventType.NOTICE]
    assert [n.data["code"] for n in notices] == ["mcp.expired"]


# ----------------------------------------------------------------- loading
async def test_loading_without_a_connection_names_the_provider(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear, connect=False)

    with pytest.raises(IntegrationNotConnectedError) as raised:
        await load_mcp_tools(setup.context, INTEGRATOR_POLICY)

    assert raised.value.meta == {"provider": "linear"}


async def test_loading_an_expired_connection_names_the_provider(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear, status="expired")

    with pytest.raises(IntegrationExpiredError) as raised:
        await load_mcp_tools(setup.context, INTEGRATOR_POLICY)

    assert raised.value.meta == {"provider": "linear"}


async def test_an_optional_load_without_a_connection_gives_no_tools_and_no_notice(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear, connect=False)

    assert await load_optional_mcp_tools(setup.context, PLANNER_POLICY) == []
    assert await setup.events(redis) == []


async def test_an_optional_load_with_an_expired_connection_gives_a_notice(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear, status="expired")

    assert await load_optional_mcp_tools(setup.context, PLANNER_POLICY) == []
    (notice,) = await setup.events(redis)
    assert (notice.type, notice.data["code"]) == (RunEventType.NOTICE, "mcp.expired")


async def test_an_optional_load_while_linear_is_down_gives_a_notice(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, linear: FakeLinear
) -> None:
    setup = await _setup(engine, app_sessions, redis, linear)
    linear.mcp_error_status = 500

    assert await load_optional_mcp_tools(setup.context, PLANNER_POLICY) == []
    (notice,) = await setup.events(redis)
    assert notice.data["code"] == "mcp.unavailable"
    assert await connection_status(engine, setup.workspace_id) == "connected"


# ------------------------------------------------------------------ secrets
async def test_no_log_line_or_event_holds_a_token_or_the_authorization_header(
    engine: AsyncEngine,
    app_sessions: Any,
    redis: Redis,
    linear: FakeLinear,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    setup = await _setup(engine, app_sessions, redis, linear)
    tools = await load_mcp_tools(setup.context, PLANNER_POLICY)
    linear.revoke_access_tokens()

    await _tool(tools, "list_issues").ainvoke({"query": "billing"})

    seen = {token for token in linear.mcp_tokens_seen if token}
    shown = caplog.text + " ".join(str(e.data) for e in await setup.events(redis))
    assert seen
    assert not any(token in shown for token in seen)
    assert "Authorization" not in shown
