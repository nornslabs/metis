"""The ``planning.plans`` and ``planning.phases`` tables (tenant tables, RLS)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7
from metis.modules.planning.models._schema import (
    IDEAS_TABLE,
    SCHEMA,
    SPEC_VERSIONS_TABLE,
    WORKSPACES_TABLE,
)


class PlanRow(Base):
    """One plan of an idea for one spec version; ``draft`` until marked ``ready``."""

    __tablename__ = "plans"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    idea_id: Mapped[UUID] = mapped_column(ForeignKey(f"{IDEAS_TABLE}.id", ondelete="CASCADE"))
    spec_version_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SPEC_VERSIONS_TABLE}.id"))
    status: Mapped[str] = mapped_column(Text, default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PhaseRow(Base):
    """One phase of a plan; ``position`` counts from 0."""

    __tablename__ = "phases"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    plan_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.plans.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text)
    exit_criteria: Mapped[str] = mapped_column(Text)
