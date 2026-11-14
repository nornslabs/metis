"""SQLAlchemy models for the ``identity`` schema (see migration ``0003_identity``)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.ids import uuid7
from metis.core.models import Base

SCHEMA = "identity"


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    auth_sub: Mapped[str] = mapped_column(Text, unique=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class WorkspaceRow(Base):
    __tablename__ = "workspaces"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(Text)
    is_personal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MemberRow(Base):
    __tablename__ = "members"
    __table_args__ = {"schema": SCHEMA}

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
