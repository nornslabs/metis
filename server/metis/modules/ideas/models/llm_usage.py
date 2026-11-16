"""The ``ideas.llm_usage`` table."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7
from metis.helpers.time import utcnow
from metis.modules.ideas.models._schema import SCHEMA, WORKSPACES_TABLE


class LlmUsageRow(Base):
    """Tokens (and cost, when a price is known) of one completed LLM call (tenant table, RLS).

    ``run_id`` has no foreign key yet: the runs table arrives with SHIP-225.
    """

    __tablename__ = "llm_usage"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    run_id: Mapped[UUID]
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    model: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
