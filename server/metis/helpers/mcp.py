"""MCP client plumbing shared by every MCP-backed provider (Exa today; Linear and
Notion later).

``open_mcp_session`` connects to a remote MCP server over streamable HTTP with a
caller-built ``httpx.AsyncClient`` (which carries the auth headers), runs the
MCP handshake and yields the ``ClientSession``. Any failure inside the block,
including tool calls, becomes a safe ``UpstreamError``.
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager

import anyio
import httpx
from mcp import ClientSession, McpError
from mcp.client.streamable_http import streamable_http_client

from metis.core.errors import UpstreamError
from metis.core.logging import get_logger
from metis.helpers.http import UNAUTHORIZED_STATUSES, FailureReason, provider_error

logger = get_logger(__name__)

_PROVIDER_FAILURES = (
    httpx.HTTPError,
    TimeoutError,
    McpError,
    anyio.ClosedResourceError,
    anyio.BrokenResourceError,
    anyio.EndOfStream,
)


@asynccontextmanager
async def open_mcp_session(
    http: httpx.AsyncClient, url: str, provider: str
) -> AsyncGenerator[ClientSession]:
    """An initialised MCP session to ``url``; provider failures raise ``UpstreamError``.

    A failure while connecting is always a provider failure. Once the session is open, only
    an exception that is itself a provider failure (HTTP, timeout, MCP protocol, closed
    stream) is mapped; any other exception raised by the block passes through unchanged, so
    a bug or a domain error in the caller is not reported as a provider problem.
    """
    connected = False
    try:
        async with (
            streamable_http_client(url, http_client=http) as (read, write, _session_id),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            connected = True
            yield session
    except UpstreamError:
        raise
    except Exception as exc:  # noqa: BLE001 - every provider failure maps to a safe reason
        leaves = list(_leaves(exc))
        if connected and not any(_is_provider_failure(leaf) for leaf in leaves):
            if len(leaves) == 1:
                raise leaves[0] from None
            raise
        reason = _reason(exc)
        logger.error(
            "mcp.session_failed",
            provider=provider,
            reason=reason.value,
            connected=connected,
            causes=describe_causes(exc),
        )
        # Chain nothing: transport errors can carry the request and its headers.
        raise provider_error(provider, reason) from None


def _leaves(exc: BaseException) -> Iterator[BaseException]:
    """The exceptions inside (possibly nested) exception groups."""
    if isinstance(exc, BaseExceptionGroup):
        for inner in exc.exceptions:
            yield from _leaves(inner)
    else:
        yield exc


def _is_provider_failure(exc: BaseException) -> bool:
    """Whether ``exc`` is the provider or the connection failing, not the caller's own error."""
    return isinstance(exc, _PROVIDER_FAILURES)


def describe_causes(exc: BaseException) -> list[str]:
    """Log-safe names of the leaf exceptions in ``exc``: each class and, when it has one, a
    status code; never a message (a message can carry an upstream body)."""
    return [_describe(leaf) for leaf in _leaves(exc)]


def _describe(exc: BaseException) -> str:
    name = f"{type(exc).__module__}.{type(exc).__qualname__}"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"{name}({exc.response.status_code})"
    if isinstance(exc, McpError):
        return f"{name}({exc.error.code})"
    return name


def _reason(exc: BaseException) -> FailureReason:
    """The most specific safe reason found among the leaf exceptions."""
    leaves = list(_leaves(exc))
    if any(
        isinstance(leaf, httpx.HTTPStatusError)
        and leaf.response.status_code in UNAUTHORIZED_STATUSES
        for leaf in leaves
    ):
        return FailureReason.UNAUTHORIZED
    if any(
        isinstance(leaf, httpx.HTTPStatusError) and leaf.response.status_code == 429
        for leaf in leaves
    ):
        return FailureReason.RATE_LIMITED
    if any(
        isinstance(leaf, httpx.HTTPStatusError) and leaf.response.status_code >= 500
        for leaf in leaves
    ):
        return FailureReason.SERVER_ERROR
    if any(isinstance(leaf, (TimeoutError, httpx.TimeoutException)) for leaf in leaves):
        return FailureReason.TIMEOUT
    if any(isinstance(leaf, httpx.TransportError) for leaf in leaves):
        return FailureReason.UNREACHABLE
    return FailureReason.BAD_RESPONSE


_STATUS_IN_MESSAGE = (
    (re.compile(r"\(40[13]\)"), FailureReason.UNAUTHORIZED),
    (re.compile(r"\(?429\)?"), FailureReason.RATE_LIMITED),
    (re.compile(r"\(?50[0-9]\)?"), FailureReason.SERVER_ERROR),
)


def failure_reason(exc: BaseException) -> FailureReason:
    """The safe reason an MCP call failed, from an adapter error, a transport error (possibly
    inside exception groups) or, last, a status code named in an error message."""
    if isinstance(exc, UpstreamError):
        try:
            return FailureReason(str((exc.meta or {}).get("reason")))
        except ValueError:
            return FailureReason.BAD_RESPONSE
    reason = _reason(exc)
    if reason is not FailureReason.BAD_RESPONSE:
        return reason
    message = str(exc)
    for pattern, matched in _STATUS_IN_MESSAGE:
        if pattern.search(message):
            return matched
    return FailureReason.BAD_RESPONSE
