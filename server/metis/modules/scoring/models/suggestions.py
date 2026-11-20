"""The ``scoring.suggestions`` table (tenant table, RLS)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7
from metis.helpers.time import utcnow
from metis.modules.scoring.models._schema import (
    IDEAS_TABLE,
    SCHEMA,
    WORKSPACES_TABLE,
)


class SuggestionRow(Base):
    """One improvement suggestion of the Advisor. The app role can only change ``status``."""

    __tablename__ = "suggestions"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    idea_id: Mapped[UUID] = mapped_column(ForeignKey(f"{IDEAS_TABLE}.id", ondelete="CASCADE"))
    score_run_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.score_runs.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    target_params: Mapped[list[str]] = mapped_column(ARRAY(Text))
    expected_impact: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
