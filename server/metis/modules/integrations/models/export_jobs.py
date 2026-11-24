"""The ``integrations.export_jobs`` table: one export's approval decision and outcome."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7
from metis.helpers.time import utcnow
from metis.modules.integrations.models._schema import SCHEMA


class ExportJobRow(Base):
    """One run's export: the preview the user saw, who decided and when, and the status."""

    __tablename__ = "export_jobs"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity.workspaces.id", ondelete="CASCADE")
    )
    idea_id: Mapped[UUID] = mapped_column(ForeignKey("ideas.ideas.id", ondelete="CASCADE"))
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("planning.plans.id", ondelete="CASCADE"))
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("ideas.workflow_runs.id", ondelete="CASCADE"), unique=True
    )
    provider: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB)
    decided_by: Mapped[UUID] = mapped_column(ForeignKey("auth.users.id"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
