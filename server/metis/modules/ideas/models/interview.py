"""The ``ideas.interview_turns`` table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7
from metis.helpers.time import utcnow
from metis.modules.ideas.models._schema import SCHEMA, WORKSPACES_TABLE


class InterviewTurnRow(Base):
    """One interview turn of an idea (tenant table, RLS), ordered by its uuid7 ``id``."""

    __tablename__ = "interview_turns"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    idea_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.ideas.id", ondelete="CASCADE"))
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.workflow_runs.id", ondelete="CASCADE")
    )
    topic: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)