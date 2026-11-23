"""Providers and connection states."""

from __future__ import annotations

from enum import StrEnum


class IntegrationProvider(StrEnum):
    """MCP providers; matches the ``mcp_connections.provider`` CHECK."""

    LINEAR = "linear"
    NOTION = "notion"


class ConnectionStatus(StrEnum):
    """Stored state of a connection; matches the ``mcp_connections.status`` CHECK."""

    CONNECTED = "connected"
    EXPIRED = "expired"
    REVOKED = "revoked"


class IntegrationStatus(StrEnum):
    """What a member sees: a revoked connection reads as ``not_connected``."""

    NOT_CONNECTED = "not_connected"
    CONNECTED = "connected"
    EXPIRED = "expired"
