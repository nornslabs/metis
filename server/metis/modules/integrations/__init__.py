"""Integrations module: MCP connections (OAuth, tokens, tool discovery). Use only what is
exported here.

An owner connects a provider (Linear) with OAuth; its tokens are stored sealed and refreshed
when used. Agent code gets tools only through ``get_mcp_client``. It also keeps the external
refs (a Metis record's id in the tool) and the record of each export's approval. Notion is not
connectable yet.
"""

from metis.modules.integrations.controller import router
from metis.modules.integrations.dto import (
    FINISHED_STATUSES,
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
    finish_export,
    get_export_decision,
    list_external_refs,
    mark_export_running,
    record_export_decision,
    save_external_ref,
)

__all__ = [
    "FINISHED_STATUSES",
    "ExportJob",
    "ExportStatus",
    "ExternalRef",
    "IntegrationProvider",
    "IntegrationStatus",
    "IntegrationView",
    "LocalKind",
    "expire_connection",
    "finish_export",
    "get_export_decision",
    "get_mcp_client",
    "list_external_refs",
    "mark_export_running",
    "record_export_decision",
    "refresh_connection",
    "save_external_ref",
    "router",
]
