"""The ``integrations.mcp_connections`` table: one MCP connection per workspace and provider."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7
from metis.helpers.time import utcnow
from metis.modules.integrations.models._schema import SCHEMA


class McpConnectionRow(Base):
    """A workspace's OAuth connection to one remote MCP server.

    ``sealed_tokens`` holds the sealed token set and the registered client (envelope
    encryption, workspace id as AAD); it is ``NULL`` once the connection is revoked.
    """

    __tablename__ = "mcp_connections"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity.workspaces.id", ondelete="CASCADE")
    )
    provider: Mapped[str] = mapped_column(Text)
    server_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    sealed_tokens: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("auth.users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
