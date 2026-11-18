"""The ``research.competitors`` table: the workspace's competitor knowledge base."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7
from metis.helpers.time import utcnow
from metis.modules.research.dto.competitors import EMBEDDING_DIMENSIONS
from metis.modules.research.models._schema import SCHEMA, WORKSPACES_TABLE


class CompetitorRow(Base):
    """A competitor, unique per workspace by its normalized ``domain`` (tenant table, RLS).

    ``embedding`` is deferred: no read ever returns it, only similarity queries use it.
    """

    __tablename__ = "competitors"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    pricing: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), deferred=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
