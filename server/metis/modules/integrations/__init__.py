"""Integrations module: MCP connections (OAuth, tokens, tool discovery). Use only what is
exported here.

An owner connects a provider (Linear) with OAuth; its tokens are stored sealed and refreshed
when used. Agent code gets tools only through ``get_mcp_client``. It also keeps the external
refs (a Metis record's id in the tool) and the record of each export's approval. Notion is not
connectable yet.
"""

from metis.modules.integrations.controller import router
from metis.modules.integrations.dto import (
    ExportJob,
    ExportStatus,
    ExternalRef,
    IntegrationProvider,
    IntegrationStatus,
    IntegrationView,
    LocalKind,
)
from metis.modules.integrations.service.connections import (
    expire_connection,
    get_mcp_client,
    refresh_connection,
)
from metis.modules.integrations.service.exports import (
    get_export_decision,
    list_external_refs,
    mark_export_running,
    record_export_decision,
    save_external_ref,
)

__all__ = [
    "ExportJob",
    "ExportStatus",
    "ExternalRef",
    "IntegrationProvider",
    "IntegrationStatus",
    "IntegrationView",
    "LocalKind",
    "expire_connection",
    "get_export_decision",
    "get_mcp_client",
    "list_external_refs",
    "mark_export_running",
    "record_export_decision",
    "refresh_connection",
    "router",
    "save_external_ref",
]
