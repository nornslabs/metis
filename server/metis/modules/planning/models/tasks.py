"""The ``planning.tasks`` and ``planning.task_deps`` tables (tenant tables, RLS)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from metis.core.models import Base
from metis.helpers.ids import uuid7
from metis.modules.planning.models._schema import SCHEMA, WORKSPACES_TABLE


class TaskRow(Base):
    """One task of a plan, ordered inside its phase by ``position``."""

    __tablename__ = "tasks"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    plan_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.plans.id", ondelete="CASCADE"))
    phase_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.phases.id"))
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    estimate: Mapped[int] = mapped_column(SmallInteger)
    labels: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    parent_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.tasks.id"), default=None
    )


class TaskDepRow(Base):
    """``task_id`` cannot start before ``blocked_by_task_id`` is done."""

    __tablename__ = "task_deps"
    __table_args__ = {"schema": SCHEMA}

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{WORKSPACES_TABLE}.id", ondelete="CASCADE")
    )
    plan_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.plans.id", ondelete="CASCADE"))
    task_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.tasks.id"), primary_key=True)
    blocked_by_task_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.tasks.id"), primary_key=True
    )
