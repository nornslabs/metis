"""Which MCP server each provider connects to, and how to talk to it."""

from __future__ import annotations

from metis.adapters.mcp import linear
from metis.adapters.mcp.linear import ToolInfo
from metis.core.errors import IntegrationProviderUnsupportedError
from metis.helpers.http import ClientFactory
from metis.modules.integrations.dto import IntegrationProvider

_SERVER_URLS = {IntegrationProvider.LINEAR: linear.SERVER_URL}


def supported_providers() -> list[IntegrationProvider]:
    """The providers that can be connected today, in display order."""
    return list(_SERVER_URLS)


def server_url(provider: IntegrationProvider) -> str:
    """The MCP server URL of ``provider``; ``IntegrationProviderUnsupportedError`` if none."""
    try:
        return _SERVER_URLS[provider]
    except KeyError:
        raise IntegrationProviderUnsupportedError(
            f"{provider.value.capitalize()} cannot be connected yet",
            meta={"provider": provider.value},
        ) from None


async def list_tools(
    make_client: ClientFactory, provider: IntegrationProvider, access_token: str
) -> list[ToolInfo]:
    """The tools ``provider``'s server offers to ``access_token``."""
    server_url(provider)
    return await linear.LinearMcpClient(make_client, access_token).list_tools()
