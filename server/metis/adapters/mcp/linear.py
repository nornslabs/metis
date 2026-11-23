"""Linear through its hosted MCP server (``https://mcp.linear.app/mcp``).

The workspace's OAuth access token goes in the ``Authorization`` header. This module lists the
server's tools (the SHIP-231 connection check); the agents load the same server's tools later
(SHIP-233).
"""

from __future__ import annotations

from metis.helpers.dto import FrozenModel
from metis.helpers.http import ClientFactory, capped
from metis.helpers.mcp import open_mcp_session

PROVIDER = "linear"
SERVER_URL = "https://mcp.linear.app/mcp"
AUTHORIZATION_HEADER = "Authorization"


class ToolInfo(FrozenModel):
    """One tool a server offers."""

    name: str
    description: str


class LinearMcpClient:
    """Linear's hosted MCP server, used with ``access_token``."""

    def __init__(self, make_client: ClientFactory, access_token: str) -> None:
        self._make_client = make_client
        self._access_token = access_token

    async def list_tools(self) -> list[ToolInfo]:
        """The server's tools; raises ``UpstreamError`` (``unauthorized`` on a rejected token)."""
        headers = {AUTHORIZATION_HEADER: f"Bearer {self._access_token}"}
        async with (
            capped(PROVIDER),
            self._make_client(headers) as http,
            open_mcp_session(http, SERVER_URL, PROVIDER) as session,
        ):
            listing = await session.list_tools()
        return [
            ToolInfo(name=tool.name, description=tool.description or "") for tool in listing.tools
        ]
