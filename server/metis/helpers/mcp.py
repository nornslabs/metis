"""MCP client plumbing shared by every MCP-backed provider (Exa today; Linear and
Notion later).

``open_mcp_session`` connects to a remote MCP server over streamable HTTP with a
caller-built ``httpx.AsyncClient`` (which carries the auth headers), runs the
MCP handshake and yields the ``ClientSession``. Any failure inside the block,
including tool calls, becomes a safe ``UpstreamError``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from metis.core.errors import UpstreamError
from metis.helpers.http import UNAUTHORIZED_STATUSES, FailureReason, provider_error


@asynccontextmanager
async def open_mcp_session(
    http: httpx.AsyncClient, url: str, provider: str
) -> AsyncIterator[ClientSession]:
    """An initialised MCP session to ``url``; failures raise ``UpstreamError``."""
    try:
        async with (
            streamable_http_client(url, http_client=http) as (read, write, _session_id),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            yield session
    except UpstreamError:
        raise
    except Exception as exc:  # noqa: BLE001 - every failure maps to a safe reason
        # Chain nothing: transport errors can carry the request and its headers.
        raise provider_error(provider, _reason(exc)) from None


def _leaves(exc: BaseException) -> Iterator[BaseException]:
    """The exceptions inside (possibly nested) exception groups."""
    if isinstance(exc, BaseExceptionGroup):
        for inner in exc.exceptions:
            yield from _leaves(inner)
    else:
        yield exc


def _reason(exc: BaseException) -> FailureReason:
    """The most specific safe reason found among the leaf exceptions."""
    leaves = list(_leaves(exc))
    if any(
        isinstance(leaf, httpx.HTTPStatusError)
        and leaf.response.status_code in UNAUTHORIZED_STATUSES
        for leaf in leaves
    ):
        return FailureReason.UNAUTHORIZED
    if any(isinstance(leaf, (TimeoutError, httpx.TimeoutException)) for leaf in leaves):
        return FailureReason.TIMEOUT
    if any(isinstance(leaf, httpx.TransportError) for leaf in leaves):
        return FailureReason.UNREACHABLE
    return FailureReason.BAD_RESPONSE
