"""The ``identity.workspace_settings`` table: per-workspace run limits."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.time import utcnow
from metis.modules.identity.models._schema import SCHEMA


class WorkspaceSettingsRow(Base):
    """Per-workspace run limits; no row means the defaults apply."""

    __tablename__ = "workspace_settings"
    __table_args__ = {"schema": SCHEMA}

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    run_budget_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    max_steps: Mapped[int] = mapped_column(Integer)
    linear_team_id: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
