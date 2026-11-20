"""The ``scoring.rubric_versions`` table (global: no tenant column, no RLS)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.time import utcnow
from metis.modules.scoring.models._schema import SCHEMA


class RubricVersionRow(Base):
    """The weights of one rubric version; ``id`` is the version number."""

    __tablename__ = "rubric_versions"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    weights: Mapped[dict[str, int]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
