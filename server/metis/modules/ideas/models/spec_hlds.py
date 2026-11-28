"""The ``ideas.spec_hlds`` table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7
from metis.helpers.time import utcnow
from metis.modules.ideas.models._schema import SCHEMA, WORKSPACES_TABLE


class SpecHldRow(Base):
    """The HLD written for one version of an idea's spec (tenant table, RLS). Never updated or
    deleted: a changed spec gets a new row."""

    __tablename__ = "spec_hlds"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    idea_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.ideas.id", ondelete="CASCADE"))
    spec_version_number: Mapped[int] = mapped_column(Integer)
    spec_hash: Mapped[str] = mapped_column(Text)
    build_language: Mapped[str] = mapped_column(Text)
    content_md: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
