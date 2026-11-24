"""MCP client plumbing shared by every MCP-backed provider (Exa today; Linear and
Notion later).

``open_mcp_session`` connects to a remote MCP server over streamable HTTP with a
caller-built ``httpx.AsyncClient`` (which carries the auth headers), runs the
MCP handshake and yields the ``ClientSession``. Any failure inside the block,
including tool calls, becomes a safe ``UpstreamError``.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from metis.core.errors import UpstreamError
from metis.helpers.http import UNAUTHORIZED_STATUSES, FailureReason, provider_error

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterator


@asynccontextmanager
async def open_mcp_session(
    http: httpx.AsyncClient, url: str, provider: str
) -> AsyncGenerator[ClientSession]:
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
    except Exception as exc:
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
