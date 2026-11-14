"""Exa through its hosted MCP server (``https://mcp.exa.ai/mcp``).

The workspace key goes in the ``x-api-key`` header. Today this only checks a
key with the smallest possible ``web_search_exa`` call; the agents load the
same server's tools later (SHIP-226).

Exa also serves keyless searches, so listing tools proves nothing about a key;
the check must call a tool. A bad key does not fail at the HTTP level: the
tool returns ``isError`` with a ``(401)`` in its text.
"""

from __future__ import annotations

from mcp.types import CallToolResult, TextContent

from metis.helpers.http import ClientFactory, FailureReason, capped, provider_error
from metis.helpers.mcp import open_mcp_session

PROVIDER = "exa"
EXA_MCP_URL = "https://mcp.exa.ai/mcp"
API_KEY_HEADER = "x-api-key"
SEARCH_TOOL = "web_search_exa"
# Field names from the server's tool schema (``query`` and ``objective`` are required).
CHECK_ARGUMENTS = {
    "query": "Metis API key check",
    "objective": "Return any one page; this only verifies the API key works.",
    "numResults": 1,
}
_AUTH_ERROR_MARKERS = ("(401)", "(403)")


class ExaMcpClient:
    """Exa's hosted MCP server, used with ``api_key``."""

    def __init__(self, make_client: ClientFactory, api_key: str) -> None:
        self._make_client = make_client
        self._api_key = api_key

    async def check(self) -> None:
        """Run one 1-result search; raises ``UpstreamError`` if the key does not work."""
        async with (
            capped(PROVIDER),
            self._make_client({API_KEY_HEADER: self._api_key}) as http,
            open_mcp_session(http, EXA_MCP_URL, PROVIDER) as session,
        ):
            result = await session.call_tool(SEARCH_TOOL, CHECK_ARGUMENTS)
        _raise_for_result(result)


def _raise_for_result(result: CallToolResult) -> None:
    """Map a failed tool result to a safe ``UpstreamError``; its text is never kept."""
    if not result.isError and result.content:
        return
    text = " ".join(part.text for part in result.content if isinstance(part, TextContent))
    if result.isError and any(marker in text for marker in _AUTH_ERROR_MARKERS):
        raise provider_error(PROVIDER, FailureReason.UNAUTHORIZED)
    raise provider_error(PROVIDER, FailureReason.BAD_RESPONSE)
