"""Postgres access for ``ideas.workflow_runs``. Queries only; no business rules.

Every query filters by ``workspace_id`` as well as relying on RLS. The one exception is
``list_running``, which exists to read across workspaces.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.ids import uuid7
from metis.modules.ideas.models import WorkflowRunRow


async def create(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    *,
    kind: str,
    idempotency_key: str | None,
) -> WorkflowRunRow:
    stmt = (
        insert(WorkflowRunRow)
        .values(
            id=uuid7(),
            workspace_id=workspace_id,
            idea_id=idea_id,
            kind=kind,
            idempotency_key=idempotency_key,
        )
        .returning(WorkflowRunRow)
    )
    return (await session.scalars(stmt)).one()


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


async def list_running(session: AsyncSession) -> list[tuple[UUID, UUID]]:
    """``(run_id, workspace_id)`` of every running run, through the ``SECURITY DEFINER``
    function that reads across workspaces."""
    result = await session.execute(
        text("SELECT run_id, workspace_id FROM ideas.list_running_runs()")
    )
    return [(row.run_id, row.workspace_id) for row in result]
