"""A ``langchain-mcp-adapters`` client over several remote MCP servers, with bearer tokens.

The agent loads tools from it (SHIP-233). Tokens go in the ``Authorization`` header only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import McpHttpClientFactory, StreamableHttpConnection

from metis.helpers.http import PROVIDER_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class McpServer:
    """One server to reach: its URL and the access token to present."""

    url: str
    access_token: str = field(repr=False)


def build_mcp_client(
    servers: Mapping[str, McpServer], httpx_client_factory: McpHttpClientFactory | None = None
) -> MultiServerMCPClient:
    """A client with one streamable-HTTP connection per named server."""
    connections: dict[str, StreamableHttpConnection] = {}
    for name, server in servers.items():
        connection = StreamableHttpConnection(
            transport="streamable_http",
            url=server.url,
            headers={"Authorization": f"Bearer {server.access_token}"},
            timeout=PROVIDER_TIMEOUT_SECONDS,
        )
        if httpx_client_factory is not None:
            connection["httpx_client_factory"] = httpx_client_factory
        connections[name] = connection
    return MultiServerMCPClient(connections)  # type: ignore[arg-type]
