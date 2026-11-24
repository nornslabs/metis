"""The ``integrations.external_refs`` table: a Metis row's id in an external tool."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7
from metis.helpers.time import utcnow
from metis.modules.integrations.models._schema import SCHEMA
from datetime import datetime
from uuid import UUID


class ExternalRefRow(Base):
    """Links a Metis record (``local_kind``, ``local_id``) to its id in an external tool."""

    __tablename__ = "external_refs"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity.workspaces.id", ondelete="CASCADE")
    )
    provider: Mapped[str] = mapped_column(Text)
    local_kind: Mapped[str] = mapped_column(Text)
    local_id: Mapped[UUID] = mapped_column()
    external_id: Mapped[str] = mapped_column(Text)
    external_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
