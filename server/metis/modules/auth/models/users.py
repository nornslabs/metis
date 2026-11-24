"""The ``auth.users`` table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7
from metis.helpers.time import utcnow
from metis.modules.auth.models._schema import SCHEMA


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    email: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)