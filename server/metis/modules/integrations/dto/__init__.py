"""Data-transfer objects of the integrations module."""

from __future__ import annotations

from metis.adapters.mcp.linear import ToolInfo
from metis.modules.integrations.dto.connect import ConnectResult, PendingConnect
from metis.modules.integrations.dto.exports import (
    FINISHED_STATUSES,
    RESULT_KEY,
    ExportFailedItem,
    ExportJob,
    ExportStatus,
    ExportSummary,
    ExportSummaryList,
    ExternalRef,
    LocalKind,
)
from metis.modules.integrations.dto.providers import (
    ConnectionStatus,
    IntegrationProvider,
    IntegrationStatus,
)
from metis.modules.integrations.dto.views import (
    ConnectRequest,
    ConnectStarted,
    IntegrationList,
    IntegrationView,
    ToolList,
)

__all__ = [
    "FINISHED_STATUSES",
    "RESULT_KEY",
    "ConnectRequest",
    "ConnectResult",
    "ConnectStarted",
    "ConnectionStatus",
    "ExportFailedItem",
    "ExportJob",
    "ExportStatus",
    "ExportSummary",
    "ExportSummaryList",
    "ExternalRef",
    "IntegrationList",
    "IntegrationProvider",
    "IntegrationStatus",
    "IntegrationView",
    "LocalKind",
    "PendingConnect",
    "ToolInfo",
    "ToolList",
]
