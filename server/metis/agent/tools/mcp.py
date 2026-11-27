"""Run-scoped tools from a connected MCP provider (Linear), for one specialist.

``load_mcp_tools`` builds the workspace's client through ``integrations.get_mcp_client`` and
returns only the tools the specialist's policy names. Every tool:

- publishes a ``tool_call`` event (provider, name, short argument summary, read or write);
- answers with at most ``MAX_RESULT_CHARS`` characters, so one big list cannot fill the context;
- for a write, runs only after the user's approval is recorded (``ApprovalLedger``);
- on an expired token, refreshes once and retries; if that fails the connection is marked
  ``expired`` and the call raises ``IntegrationExpiredError`` (or, for a specialist that does
  not require the provider, answers that the provider is unavailable and the run goes on);
- retries a read once after a transient failure, never a write (a retry could duplicate it).

Tools open a short MCP session per call, so no session stays open across a pause for the user
(``interrupt()``) or after the step; nothing here needs closing.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import McpHttpClientFactory
from redis.asyncio import Redis

from metis.adapters.feature_flags import build_feature_flag_provider
from metis.agent.tools.mcp_policy import ApprovalLedger, McpToolPolicy, McpWriteRefused
from metis.agent.tools.research_kb import SessionOpener
from metis.core.config import get_settings
from metis.core.errors import (
    IntegrationExpiredError,
    IntegrationNotConnectedError,
    UpstreamError,
)
from metis.core.events import RunEventType, publish
from metis.core.logging import get_logger
from metis.core.ports import FlagContext
from metis.helpers.http import ClientFactory, FailureReason, provider_error
from metis.helpers.mcp import failure_reason
from metis.modules import integrations
from metis.modules.integrations import IntegrationProvider

TOOL_TIMEOUT_SECONDS = 20
MAX_RESULT_CHARS = 4_000
MAX_SUMMARY_CHARS = 120
RETRY_DELAY_SECONDS = 0.2
UNAVAILABLE_TEXT = "Linear is unavailable right now. Carry on without it."
NOTICE_EXPIRED = "mcp.expired"
NOTICE_EXPIRED_TEXT = "Linear is not available: the connection expired. Reconnect it in Settings."
NOTICE_UNAVAILABLE = "mcp.unavailable"
NOTICE_UNAVAILABLE_TEXT = "Linear is not available right now, so it was not used."
_SUMMARY_KEYS = ("query", "name", "title", "team", "id")
_TRANSIENT = frozenset(
    {
        FailureReason.TIMEOUT,
        FailureReason.RATE_LIMITED,
        FailureReason.SERVER_ERROR,
        FailureReason.UNREACHABLE,
    }
)

logger = get_logger(__name__)


class ToolKind(StrEnum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class McpRunContext:
    """What the tools need from the run: ids, a workspace-scoped session opener, Redis for
    events, the client factory for token refresh and, in tests, the MCP transport factory."""

    workspace_id: UUID
    run_id: UUID
    open_session: SessionOpener
    redis: Redis
    make_client: ClientFactory
    mcp_http_client: McpHttpClientFactory | None = None
    specialist: str = ""


async def load_mcp_tools(
    context: McpRunContext,
    policy: McpToolPolicy,
    ledger: ApprovalLedger | None = None,
    *,
    provider: IntegrationProvider = IntegrationProvider.LINEAR,
) -> list[BaseTool]:
    """The provider's tools this ``policy`` allows, wrapped as described in the module docs.

    Raises ``IntegrationNotConnectedError`` / ``IntegrationExpiredError`` (naming the provider)
    when there is no usable connection, and ``UpstreamError`` when the provider fails.
    """
    _flags = build_feature_flag_provider(get_settings())
    settings = get_settings()
    flag_context = FlagContext(
        workspace_id=context.workspace_id,
        environment=settings.app_env,
        custom_attributes={},
    )
    if not await _flags.is_enabled(
        f"{provider.value}_enabled", flag_context, default=True
    ):
        logger.info(
            "integration.skipped_provider_disabled",
            provider=provider.value,
        )
        return []
    if not policy.allowed:
        return []
    connection = _Connection(context, provider, policy, ledger or ApprovalLedger())
    return await connection.load()


async def load_optional_mcp_tools(
    context: McpRunContext,
    policy: McpToolPolicy,
    *,
    provider: IntegrationProvider = IntegrationProvider.LINEAR,
) -> list[BaseTool]:
    """Like ``load_mcp_tools`` for a specialist that works without the provider: no usable
    connection gives no tools (a ``notice`` says why when it lapsed or the provider is down)."""
    try:
        return await load_mcp_tools(context, policy, provider=provider)
    except IntegrationNotConnectedError:
        return []
    except IntegrationExpiredError:
        await _notice(context, NOTICE_EXPIRED, NOTICE_EXPIRED_TEXT)
    except UpstreamError:
        await _notice(context, NOTICE_UNAVAILABLE, NOTICE_UNAVAILABLE_TEXT)
    return []


def summarize_args(arguments: Mapping[str, Any]) -> str:
    """A short, safe description of a call's arguments for the ``tool_call`` event."""
    for key in _SUMMARY_KEYS:
        value = arguments.get(key)
        if isinstance(value, str | int) and str(value).strip():
            return f"{key}: {value}"[:MAX_SUMMARY_CHARS]
    names = ", ".join(sorted(arguments))
    return (f"args: {names}" if names else "no arguments")[:MAX_SUMMARY_CHARS]


def truncate_result(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    """``text`` cut to ``limit`` characters with a marker saying how much was dropped."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… [truncated {len(text) - limit} characters]"


class _Connection:
    """The loaded tools of one provider, rebuilt with a new token after a refresh."""

    def __init__(
        self,
        context: McpRunContext,
        provider: IntegrationProvider,
        policy: McpToolPolicy,
        ledger: ApprovalLedger,
    ) -> None:
        self._context = context
        self._provider = provider
        self._policy = policy
        self._ledger = ledger
        self._client: MultiServerMCPClient | None = None
        self._tools: dict[str, BaseTool] = {}
        self._notified = False

    async def load(self) -> list[BaseTool]:
        await self._build(refresh=False)
        listed = await self._guarded(self._list, ToolKind.READ)
        self._tools = _allowed(listed, self._policy.allowed)
        for missing in sorted(self._policy.allowed - set(self._tools)):
            logger.warning("mcp.tool_missing", provider=self._provider.value, tool=missing)
        logger.info(
            "mcp.tools_loaded",
            provider=self._provider.value,
            specialist=self._context.specialist,
            count=len(self._tools),
        )
        return [self._wrap(name) for name in sorted(self._tools)]

    async def _build(self, *, refresh: bool) -> None:
        """A client with a fresh token; ``refresh`` forces a token refresh first."""
        context = self._context
        failure: IntegrationExpiredError | None = None
        async with context.open_session(context.workspace_id) as session:
            try:
                if refresh:
                    await integrations.refresh_connection(
                        session, context.make_client, context.workspace_id, self._provider
                    )
                self._client = await integrations.get_mcp_client(
                    session,
                    context.make_client,
                    context.workspace_id,
                    [self._provider],
                    httpx_client_factory=context.mcp_http_client,
                )
            except IntegrationExpiredError as exc:
                failure = exc  # raised after the block: the session commits the new status
        if failure is not None:
            logger.info("mcp.expired", provider=self._provider.value)
            raise failure

    async def _list(self) -> list[BaseTool]:
        client = self._require_client()
        return await client.get_tools(server_name=self._provider.value)

    def _require_client(self) -> MultiServerMCPClient:
        if self._client is None:
            raise provider_error(self._provider.value, FailureReason.BAD_RESPONSE)
        return self._client

    async def _guarded[T](self, operation: Callable[[], Awaitable[T]], kind: ToolKind) -> T:
        """Run ``operation`` with the timeout, one refresh on 401 and one retry of a read."""
        refreshed = False
        retried = False
        while True:
            try:
                async with asyncio.timeout(TOOL_TIMEOUT_SECONDS):
                    return await operation()
            except Exception as exc:  # noqa: BLE001 - MCP errors are normalized below
                reason = failure_reason(exc)
                if reason is FailureReason.UNAUTHORIZED:
                    if refreshed:
                        raise await self._expire() from None
                    refreshed = True
                    await self._refresh_and_reload()
                    continue
                if kind is ToolKind.READ and reason in _TRANSIENT and not retried:
                    retried = True
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue
                raise provider_error(self._provider.value, reason) from None

    async def _refresh_and_reload(self) -> None:
        """Refresh the token, then point the loaded tools at a client that carries it."""
        await self._build(refresh=True)
        if not self._tools:
            return
        try:
            listed = await self._list()
        except Exception as exc:  # noqa: BLE001 - MCP errors are normalized below
            reason = failure_reason(exc)
            if reason is FailureReason.UNAUTHORIZED:
                raise await self._expire() from None
            raise provider_error(self._provider.value, reason) from None
        self._tools = _allowed(listed, frozenset(self._tools))

    async def _expire(self) -> IntegrationExpiredError:
        context = self._context
        async with context.open_session(context.workspace_id) as session:
            error = await integrations.expire_connection(
                session, context.workspace_id, self._provider
            )
        logger.info("mcp.expired", provider=self._provider.value)
        return error

    def _wrap(self, name: str) -> BaseTool:
        source = self._tools[name]
        kind = ToolKind.WRITE if name in self._policy.write else ToolKind.READ

        async def invoke(**arguments: Any) -> str:
            if kind is ToolKind.WRITE:
                self._refuse_unapproved(name)
            await self._announce(name, arguments, kind)
            try:
                result = await self._guarded(
                    lambda: self._tools[name].ainvoke(dict(arguments)), kind
                )
            except IntegrationExpiredError:
                if self._policy.required:
                    raise
                await self._notify_once(NOTICE_EXPIRED, NOTICE_EXPIRED_TEXT)
                return UNAVAILABLE_TEXT
            return truncate_result(_as_text(result))

        return StructuredTool.from_function(
            coroutine=invoke,
            name=name,
            description=source.description or "",
            args_schema=source.args_schema,
        )

    def _refuse_unapproved(self, name: str) -> None:
        try:
            self._ledger.require()
        except McpWriteRefused:
            logger.warning("mcp.write_refused", provider=self._provider.value, tool=name)
            raise

    async def _announce(self, name: str, arguments: Mapping[str, Any], kind: ToolKind) -> None:
        await publish(
            str(self._context.run_id),
            RunEventType.TOOL_CALL,
            {
                "provider": self._provider.value,
                "name": name,
                "summary": summarize_args(arguments),
                "kind": kind.value,
            },
            redis=self._context.redis,
        )

    async def _notify_once(self, code: str, text: str) -> None:
        if not self._notified:
            self._notified = True
            await _notice(self._context, code, text)


def _allowed(listed: list[BaseTool], names: frozenset[str]) -> dict[str, BaseTool]:
    return {tool.name: tool for tool in listed if tool.name in names}


async def _notice(context: McpRunContext, code: str, text: str) -> None:
    await publish(
        str(context.run_id),
        RunEventType.NOTICE,
        {"code": code, "text": text},
        redis=context.redis,
    )


def _as_text(result: object) -> str:
    """A tool result as text: strings as they are, content blocks joined, the rest as JSON."""
    if isinstance(result, tuple) and len(result) == 2:
        result = result[0]
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        parts = [
            block if isinstance(block, str) else str(block.get("text", ""))
            for block in result
            if isinstance(block, str) or isinstance(block, dict)
        ]
        if parts:
            return "\n".join(part for part in parts if part)
    return json.dumps(result, default=str)
