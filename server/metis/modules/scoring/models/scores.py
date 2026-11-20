"""The ``scoring.score_runs`` and ``scoring.score_params`` tables (tenant tables, RLS)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7
from metis.helpers.time import utcnow
from metis.modules.scoring.models._schema import (
    IDEAS_TABLE,
    RUNS_TABLE,
    SCHEMA,
    WORKSPACES_TABLE,
)


class ScoreRunRow(Base):
    """One immutable score of an idea; the app role can only read and insert it."""

    __tablename__ = "score_runs"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    idea_id: Mapped[UUID] = mapped_column(ForeignKey(f"{IDEAS_TABLE}.id", ondelete="CASCADE"))
    run_id: Mapped[UUID] = mapped_column(ForeignKey(f"{RUNS_TABLE}.id", ondelete="CASCADE"))
    rubric_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(f"{SCHEMA}.rubric_versions.id")
    )
    trigger: Mapped[str] = mapped_column(Text)
    total: Mapped[int] = mapped_column(Integer)
    band: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScoreParamRow(Base):
    """One parameter's result inside a score run; immutable like its run."""

    __tablename__ = "score_params"
    __table_args__ = {"schema": SCHEMA}

    score_run_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.score_runs.id", ondelete="CASCADE"), primary_key=True
    )
    param: Mapped[str] = mapped_column(Text, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    raw: Mapped[int] = mapped_column(Integer)
    weighted: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    reason: Mapped[str] = mapped_column(Text)
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    no_evidence: Mapped[bool] = mapped_column(Boolean)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
