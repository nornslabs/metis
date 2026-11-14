"""SQLAlchemy models for the ``identity`` schema (``0003_identity``, ``0005_provider_keys``)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7

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


class ProviderKeyRow(Base):
    """One sealed BYO key per workspace and kind (``llm``, ``exa``)."""

    __tablename__ = "provider_keys"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.workspaces.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    sealed: Mapped[dict[str, Any]] = mapped_column(JSONB)
    masked: Mapped[str] = mapped_column(Text)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class WorkspaceSettingsRow(Base):
    """Per-workspace run limits; no row means the defaults apply."""

    __tablename__ = "workspace_settings"
    __table_args__ = {"schema": SCHEMA}

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    run_budget_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    max_steps: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
