"""Shared HTTP plumbing for provider adapters (LLM, Exa MCP).

``provider_http_factory`` is the FastAPI dependency that hands a request a
``ClientFactory``; adapters build one short-lived ``httpx.AsyncClient`` per
call with it (the Exa MCP client needs its key as a client header). Tests
override the dependency to route calls to fakes.

``capped`` limits a whole provider call to ``PROVIDER_TIMEOUT_SECONDS``.
``send`` maps every transport or status failure to an ``UpstreamError`` whose
``meta`` names the provider and a safe reason. Keys, headers and upstream
bodies never reach the error or the logs.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Any

import httpx

from metis.core.errors import UpstreamError

PROVIDER_TIMEOUT_SECONDS = 10.0
UNAUTHORIZED_STATUSES = frozenset({401, 403})

ClientFactory = Callable[[Mapping[str, str]], httpx.AsyncClient]


class FailureReason(StrEnum):
    UNAUTHORIZED = "unauthorized"
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    BAD_RESPONSE = "bad_response"


_DETAILS = {
    FailureReason.UNAUTHORIZED: "The provider rejected the key.",
    FailureReason.UNREACHABLE: "The provider could not be reached.",
    FailureReason.TIMEOUT: "The provider did not answer in time.",
    FailureReason.BAD_RESPONSE: "The provider sent an unexpected response.",
}


def provider_error(provider: str, reason: FailureReason) -> UpstreamError:
    """An ``UpstreamError`` carrying only the provider name and a safe reason."""
    return UpstreamError(_DETAILS[reason], meta={"provider": provider, "reason": reason.value})


def make_provider_client(headers: Mapping[str, str]) -> httpx.AsyncClient:
    """A client for one provider call: ``headers`` on every request, no redirects.

    Its timeout bounds each phase (connect, read, ...); ``capped`` bounds the call.
    """
    return httpx.AsyncClient(
        headers=dict(headers), timeout=PROVIDER_TIMEOUT_SECONDS, follow_redirects=False
    )


def provider_http_factory() -> ClientFactory:
    """FastAPI dependency: how adapters create their HTTP clients."""
    return make_provider_client


@asynccontextmanager
async def capped(provider: str) -> AsyncGenerator[None]:
    """Run the block within ``PROVIDER_TIMEOUT_SECONDS`` in total, or raise ``timeout``."""
    try:
        async with asyncio.timeout(PROVIDER_TIMEOUT_SECONDS):
            yield
    except (TimeoutError, httpx.TimeoutException):
        raise provider_error(provider, FailureReason.TIMEOUT) from None


async def send(http: httpx.AsyncClient, provider: str, request: httpx.Request) -> Any:
    """Send ``request`` and return its JSON body, or raise a safe ``UpstreamError``.

    The whole call, body included, is capped at ``PROVIDER_TIMEOUT_SECONDS``.
    """
    try:
        async with capped(provider):
            response = await http.send(request)
    except httpx.HTTPError:
        # Chain nothing: transport errors can carry the request and its headers.
        raise provider_error(provider, FailureReason.UNREACHABLE) from None
    if response.status_code in UNAUTHORIZED_STATUSES:
        raise provider_error(provider, FailureReason.UNAUTHORIZED)
    if not response.is_success:
        raise provider_error(provider, FailureReason.BAD_RESPONSE)
    try:
        return response.json()
    except ValueError:
        raise provider_error(provider, FailureReason.BAD_RESPONSE) from None
