"""Postgres access for ``ideas.workflow_runs``. Queries only; no business rules.

Every query filters by ``workspace_id`` as well as relying on RLS. The one exception is
``list_running``, which exists to read across workspaces.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import ReturningInsert

from metis.core.db import insert_or_none
from metis.helpers.ids import uuid7
from metis.modules.ideas.models import WorkflowRunRow


async def create(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    *,
    kind: str,
    idempotency_key: str | None,
    user_prompt: str | None = None,
) -> WorkflowRunRow:
    return (
        await session.scalars(_insert(workspace_id, idea_id, kind, idempotency_key, user_prompt))
    ).one()


async def create_or_none(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    *,
    kind: str,
    idempotency_key: str | None,
    user_prompt: str | None = None,
) -> WorkflowRunRow | None:
    """Like ``create``; ``None`` when the idempotency key or the one-active-run index conflicts."""
    return await insert_or_none(
        session, _insert(workspace_id, idea_id, kind, idempotency_key, user_prompt)
    )


async def get_by_key(
    session: AsyncSession, workspace_id: UUID, idempotency_key: str
) -> WorkflowRunRow | None:
    stmt = select(WorkflowRunRow).where(
        WorkflowRunRow.workspace_id == workspace_id,
        WorkflowRunRow.idempotency_key == idempotency_key,
    )
    return (await session.scalars(stmt.execution_options(populate_existing=True))).one_or_none()


async def get_active_for_idea(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, active: tuple[str, ...]
) -> WorkflowRunRow | None:
    """The idea's run whose status is in ``active``, if any (the index allows one)."""
    stmt = select(WorkflowRunRow).where(
        WorkflowRunRow.workspace_id == workspace_id,
        WorkflowRunRow.idea_id == idea_id,
        WorkflowRunRow.status.in_(active),
    )
    return (await session.scalars(stmt.execution_options(populate_existing=True))).first()


async def list_page(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    *,
    after: tuple[datetime, UUID] | None,
    limit: int,
) -> list[WorkflowRunRow]:
    """Up to ``limit`` runs of the idea, newest first, strictly after the ``after`` position."""
    stmt = select(WorkflowRunRow).where(
        WorkflowRunRow.workspace_id == workspace_id, WorkflowRunRow.idea_id == idea_id
    )
    if after is not None:
        stmt = stmt.where(tuple_(WorkflowRunRow.created_at, WorkflowRunRow.id) < tuple_(*after))
    stmt = stmt.order_by(WorkflowRunRow.created_at.desc(), WorkflowRunRow.id.desc()).limit(limit)
    return list((await session.scalars(stmt)).all())


def _insert(
    workspace_id: UUID,
    idea_id: UUID,
    kind: str,
    idempotency_key: str | None,
    user_prompt: str | None,
) -> ReturningInsert[WorkflowRunRow]:
    return (
        insert(WorkflowRunRow)
        .values(
            id=uuid7(),
            workspace_id=workspace_id,
            idea_id=idea_id,
            kind=kind,
            idempotency_key=idempotency_key,
            user_prompt=user_prompt,
        )
        .returning(WorkflowRunRow)
    )


async def get(session: AsyncSession, workspace_id: UUID, run_id: UUID) -> WorkflowRunRow | None:
    stmt = select(WorkflowRunRow).where(
        WorkflowRunRow.id == run_id, WorkflowRunRow.workspace_id == workspace_id
    )
    return (await session.scalars(stmt.execution_options(populate_existing=True))).one_or_none()


async def change_status(
    session: AsyncSession,
    workspace_id: UUID,
    run_id: UUID,
    *,
    expected: str,
    values: dict[str, Any],
) -> WorkflowRunRow | None:
    """Apply ``values`` (bumping ``version``) only while the run is still ``expected``.

    ``None`` means the run changed under the caller (or does not exist).
    """
    stmt = (
        update(WorkflowRunRow)
        .where(
            WorkflowRunRow.id == run_id,
            WorkflowRunRow.workspace_id == workspace_id,
            WorkflowRunRow.status == expected,
        )
        .values(**values, version=WorkflowRunRow.version + 1)
        .returning(WorkflowRunRow)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one_or_none()


async def touch(session: AsyncSession, workspace_id: UUID, run_id: UUID) -> None:
    """Set ``updated_at`` to now while the run is ``running`` (no version bump)."""
    await session.execute(
        update(WorkflowRunRow)
        .where(
            WorkflowRunRow.id == run_id,
            WorkflowRunRow.workspace_id == workspace_id,
            WorkflowRunRow.status == "running",
        )
        .values(updated_at=func.now())
    )


async def list_running(session: AsyncSession) -> list[tuple[UUID, UUID, datetime]]:
    """``(run_id, workspace_id, updated_at)`` of every running run, through the
    ``SECURITY DEFINER`` function that reads across workspaces."""
    result = await session.execute(
        text("SELECT run_id, workspace_id, updated_at FROM ideas.list_running_runs()")
    )
    return [(row.run_id, row.workspace_id, row.updated_at) for row in result]
