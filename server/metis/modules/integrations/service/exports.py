"""Export records: external references and the decision on each run's export.

Every function takes the caller's ``AsyncSession`` (already scoped to the workspace), flushes
but never commits.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.db import set_workspace
from metis.core.errors import ConflictError
from metis.core.logging import get_logger
from metis.modules.integrations import repo
from metis.modules.integrations.dto import (
    ExportJob,
    ExportStatus,
    ExternalRef,
    IntegrationProvider,
    LocalKind,
)

logger = get_logger(__name__)


async def list_external_refs(
    session: AsyncSession,
    workspace_id: UUID,
    provider: IntegrationProvider,
    local_kind: LocalKind,
    local_ids: Collection[UUID],
) -> dict[UUID, ExternalRef]:
    """The external refs of ``local_kind`` records among ``local_ids``, keyed by local id."""
    await set_workspace(session, workspace_id)
    rows = await repo.external_refs.list_for(
        session, workspace_id, provider.value, local_kind.value, local_ids
    )
    return {row.local_id: ExternalRef.model_validate(row) for row in rows}


async def record_export_decision(
    session: AsyncSession,
    workspace_id: UUID,
    *,
    idea_id: UUID,
    plan_id: UUID,
    run_id: UUID,
    approved: bool,
    decided_by: UUID,
    decided_at: datetime,
    summary: dict[str, Any],
    provider: IntegrationProvider = IntegrationProvider.LINEAR,
) -> ExportJob:
    """Record who approved or declined the run's export. Idempotent per run: a second call for
    the same run returns the stored job and changes nothing."""
    await set_workspace(session, workspace_id)
    status = ExportStatus.APPROVED if approved else ExportStatus.DECLINED
    row = await repo.export_jobs.create_once(
        session,
        workspace_id,
        idea_id=idea_id,
        plan_id=plan_id,
        run_id=run_id,
        provider=provider.value,
        status=status.value,
        summary=summary,
        decided_by=decided_by,
        decided_at=decided_at,
    )
    if row is None:
        row = await repo.export_jobs.get_by_run(session, workspace_id, run_id)
    if row is None:  # the insert conflicted, so the run's job exists; only a race can land here
        raise ConflictError("The export decision could not be recorded; try again")
    return ExportJob.model_validate(row)


async def get_export_decision(
    session: AsyncSession, workspace_id: UUID, run_id: UUID
) -> ExportJob | None:
    """The decision already recorded for the run, or ``None`` before the user answered."""
    await set_workspace(session, workspace_id)
    row = await repo.export_jobs.get_by_run(session, workspace_id, run_id)
    return None if row is None else ExportJob.model_validate(row)
