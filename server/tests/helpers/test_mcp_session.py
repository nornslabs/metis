"""``open_mcp_session``: which failures become a provider error, and what is logged.

Seam: the session helper against the in-process Exa MCP server. A failure while connecting, or
one that is the provider's or the connection's, becomes a safe ``UpstreamError`` and is logged by
class only; any other exception raised by the caller's block passes through unchanged.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from structlog.testing import capture_logs

from metis.core.errors import UpstreamError
from metis.helpers.http import FailureReason
from metis.helpers.mcp import open_mcp_session
from tests.modules.identity.fake_exa_mcp import ExaMode, FakeExaMcp

URL = "http://exa.test/mcp"
SECRET = "sk-secret-key"


@pytest_asyncio.fixture
async def exa() -> AsyncIterator[FakeExaMcp]:
    async with FakeExaMcp().running() as fake:
        yield fake


def _client(exa: FakeExaMcp) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=exa.transport(), headers={"x-api-key": SECRET})


async def test_a_block_that_raises_its_own_error_is_not_reported_as_a_provider_error(
    exa: FakeExaMcp,
) -> None:
    with capture_logs() as logs, pytest.raises(ValueError, match="boom"):
        async with _client(exa) as http, open_mcp_session(http, URL, "exa"):
            raise ValueError("boom")

    assert logs == []


async def test_a_connection_failure_is_a_provider_error_with_its_reason(exa: FakeExaMcp) -> None:
    exa.mode = ExaMode.HTTP_401

    with pytest.raises(UpstreamError) as caught:
        async with _client(exa) as http, open_mcp_session(http, URL, "exa"):
            pytest.fail("the session must not open")

    assert (caught.value.meta or {})["reason"] == FailureReason.UNAUTHORIZED.value


async def test_a_provider_failure_in_the_block_is_mapped_and_logged_without_secrets(
    exa: FakeExaMcp,
) -> None:
    with capture_logs() as logs, pytest.raises(UpstreamError) as caught:
        async with _client(exa) as http, open_mcp_session(http, URL, "exa"):
            raise httpx.ReadTimeout(f"timed out calling with {SECRET}")

    assert (caught.value.meta or {})["reason"] == FailureReason.TIMEOUT.value
    [entry] = [log for log in logs if log["event"] == "mcp.session_failed"]
    assert entry["provider"] == "exa"
    assert entry["reason"] == FailureReason.TIMEOUT.value
    assert entry["connected"] is True
    assert entry["causes"] == ["httpx.ReadTimeout"]
    assert SECRET not in str(logs)


async def test_an_upstream_error_from_the_block_is_not_mapped_again(exa: FakeExaMcp) -> None:
    original = UpstreamError("down", meta={"provider": "exa", "reason": "rate_limited"})

    with capture_logs() as logs, pytest.raises(UpstreamError) as caught:
        async with _client(exa) as http, open_mcp_session(http, URL, "exa"):
            raise original

    assert caught.value is original
    assert logs == []


async def test_a_lone_error_inside_an_exception_group_passes_through_as_itself(
    exa: FakeExaMcp,
) -> None:
    with pytest.raises(ValueError, match="boom"):
        async with _client(exa) as http, open_mcp_session(http, URL, "exa"):
            raise ExceptionGroup("wrapped", [ValueError("boom")])
