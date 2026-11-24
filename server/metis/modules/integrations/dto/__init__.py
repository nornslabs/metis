"""Data-transfer objects of the integrations module."""

from __future__ import annotations

from metis.adapters.mcp.linear import ToolInfo
from metis.modules.integrations.dto.connect import ConnectResult, PendingConnect
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
    "ConnectRequest",
    "ConnectResult",
    "ConnectStarted",
    "ConnectionStatus",
    "IntegrationList",
    "IntegrationProvider",
    "IntegrationStatus",
    "IntegrationView",
    "PendingConnect",
    "ToolInfo",
    "ToolList",
]
