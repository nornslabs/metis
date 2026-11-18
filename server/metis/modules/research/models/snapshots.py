"""The ``research.snapshots``, ``research.items`` and ``research.idea_competitors`` tables."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7
from metis.helpers.time import utcnow
from metis.modules.research.models._schema import (
    IDEAS_TABLE,
    RUNS_TABLE,
    SCHEMA,
    WORKSPACES_TABLE,
)


class SnapshotRow(Base):
    """One research version of an idea (tenant table, RLS); immutable once ``closed_at`` is set."""

    __tablename__ = "snapshots"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    idea_id: Mapped[UUID] = mapped_column(ForeignKey(f"{IDEAS_TABLE}.id", ondelete="CASCADE"))
    run_id: Mapped[UUID] = mapped_column(ForeignKey(f"{RUNS_TABLE}.id", ondelete="CASCADE"))
    summary: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ItemRow(Base):
    """One sourced finding of a snapshot (tenant table, RLS), ordered by its uuid7 ``id``."""

    __tablename__ = "items"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.snapshots.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[date | None] = mapped_column(Date)
    quote: Mapped[str | None] = mapped_column(Text)
    claim: Mapped[str] = mapped_column(Text)
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IdeaCompetitorRow(Base):
    """A competitor a snapshot found for its idea, with its ``overlap`` 0–1 (tenant table, RLS)."""

    __tablename__ = "idea_competitors"
    __table_args__ = {"schema": SCHEMA}

    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.snapshots.id", ondelete="CASCADE"), primary_key=True
    )
    competitor_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.competitors.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    idea_id: Mapped[UUID] = mapped_column(ForeignKey(f"{IDEAS_TABLE}.id", ondelete="CASCADE"))
    overlap: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
