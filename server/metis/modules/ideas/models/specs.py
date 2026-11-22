"""The ``ideas.spec_versions`` table."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7
from metis.helpers.time import utcnow
from metis.modules.ideas.models._schema import SCHEMA, USERS_TABLE, WORKSPACES_TABLE


class SpecVersionRow(Base):
    """One version of an idea's spec (tenant table, RLS). Never updated or deleted."""

    __tablename__ = "spec_versions"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    idea_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.ideas.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(Text)
    content_md: Mapped[str] = mapped_column(Text)
    sections: Mapped[dict[str, Any]] = mapped_column(JSONB)
    run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.workflow_runs.id", ondelete="SET NULL")
    )
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey(f"{USERS_TABLE}.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
