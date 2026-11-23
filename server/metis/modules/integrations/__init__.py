"""Integrations module: MCP connections (OAuth, tokens, tool discovery). Use only what is
exported here.

An owner connects a provider (Linear) with OAuth; its tokens are stored sealed and refreshed
when used. Agent code gets tools only through ``get_mcp_client``. Notion is not connectable yet.
"""

from metis.modules.integrations.controller import router
from metis.modules.integrations.dto import IntegrationProvider, IntegrationStatus, IntegrationView
from metis.modules.integrations.service.connections import get_mcp_client

__all__ = [
    "IntegrationProvider",
    "IntegrationStatus",
    "IntegrationView",
    "get_mcp_client",
    "router",
]
