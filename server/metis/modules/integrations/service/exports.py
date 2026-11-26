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
from metis.core.outbox import add_event
from metis.helpers.time import utcnow
from metis.modules.integrations import repo
from metis.modules.integrations.dto import (
    FINISHED_STATUSES,
    RESULT_KEY,
    ExportFailedItem,
    ExportJob,
    ExportStatus,
    ExportSummary,
    ExportSummaryList,
    ExternalRef,
    IntegrationProvider,
    LocalKind,
)
from metis.modules.integrations.events import ExportFinishedPayload, export_finished

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


async def save_external_ref(
    session: AsyncSession,
    workspace_id: UUID,
    provider: IntegrationProvider,
    local_kind: LocalKind,
    local_id: UUID,
    external_id: str,
    external_url: str | None,
) -> ExternalRef:
    """Record (or update) a Metis record's id in the external tool. One row per record: a second
    save for the same record changes its Linear id and url and adds nothing."""
    await set_workspace(session, workspace_id)
    row = await repo.external_refs.upsert(
        session, workspace_id, provider.value, local_kind.value, local_id, external_id, external_url
    )
    return ExternalRef.model_validate(row)


async def mark_export_running(session: AsyncSession, workspace_id: UUID, run_id: UUID) -> ExportJob:
    """Move the run's approved export to ``running`` as its writes start. Idempotent: a job
    already ``running`` is returned unchanged. A run with no approved export is a conflict."""
    await set_workspace(session, workspace_id)
    row = await repo.export_jobs.mark_running(
        session,
        workspace_id,
        run_id,
        from_status=ExportStatus.APPROVED.value,
        to_status=ExportStatus.RUNNING.value,
    )
    if row is None:
        raise ConflictError("The run has no approved export to start")
    return ExportJob.model_validate(row)


async def finish_export(
    session: AsyncSession,
    workspace_id: UUID,
    run_id: UUID,
    status: ExportStatus,
    result: dict[str, Any],
) -> ExportJob:
    """End the run's ``running`` export as ``succeeded``, ``partial`` or ``failed``, keeping the
    preview in ``summary`` and adding ``result`` (counts, failed items, the project URL).

    Idempotent: a job that is not ``running`` is returned as it is and nothing is written, so a
    re-run never writes ``ExportFinished`` twice. The event is written, in the same transaction,
    only by the call that moves the job to ``succeeded``.
    """
    if status not in FINISHED_STATUSES:
        raise ValueError(f"An export cannot be finished as {status.value}")
    await set_workspace(session, workspace_id)
    current = await repo.export_jobs.get_by_run(session, workspace_id, run_id)
    if current is None:
        raise ConflictError("The run has no export to finish")
    row = await repo.export_jobs.mark_finished(
        session,
        workspace_id,
        run_id,
        status=status.value,
        summary={**current.summary, RESULT_KEY: result},
        finished_at=utcnow(),
    )
    if row is None:
        return ExportJob.model_validate(current)
    if status is ExportStatus.SUCCEEDED:
        add_event(
            session,
            export_finished(
                workspace_id,
                ExportFinishedPayload(
                    idea_id=row.idea_id,
                    plan_id=row.plan_id,
                    project_url=result.get("project_url"),
                    created=int(result.get("created", 0)),
                    updated=int(result.get("updated", 0)),
                ),
            ),
        )
    logger.info("export.finished", workspace_id=str(workspace_id), status=status.value)
    return ExportJob.model_validate(row)


async def export_summaries(
    session: AsyncSession,
    workspace_id: UUID,
    idea_ids: Collection[UUID],
    provider: IntegrationProvider = IntegrationProvider.LINEAR,
) -> ExportSummaryList:
    """The newest finished export of each idea in ``idea_ids``. Ideas with no finished export
    are left out."""
    await set_workspace(session, workspace_id)
    rows = await repo.export_jobs.list_latest_finished(
        session,
        workspace_id,
        provider.value,
        idea_ids,
        [status.value for status in FINISHED_STATUSES],
    )
    return ExportSummaryList(items=[_summary(ExportJob.model_validate(row)) for row in rows])


def _summary(job: ExportJob) -> ExportSummary:
    result = job.result
    return ExportSummary(
        idea_id=job.idea_id,
        status=job.status,
        project_url=_text_or_none(result.get("project_url")),
        created=_count(result.get("created")),
        updated=_count(result.get("updated")),
        links=_count(result.get("links")),
        failed=_failed_items(result.get("failed")),
        finished_at=job.finished_at,
    )


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _failed_items(value: object) -> list[ExportFailedItem]:
    if not isinstance(value, list):
        return []
    return [
        ExportFailedItem(
            kind=str(item.get("kind", "")),
            name=str(item.get("name", "")),
            reason=str(item.get("reason", "")),
        )
        for item in value
        if isinstance(item, dict)
    ]
