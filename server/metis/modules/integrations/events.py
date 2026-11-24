"""Domain events of the integrations module."""

from __future__ import annotations

from uuid import UUID

from metis.core.outbox import DomainEvent, DomainEventType
from metis.helpers.dto import FrozenModel


class ExportFinishedPayload(FrozenModel):
    """``ExportFinished``: an export that created or updated everything in the plan."""

    idea_id: UUID
    plan_id: UUID
    project_url: str | None
    created: int
    updated: int


def export_finished(workspace_id: UUID, payload: ExportFinishedPayload) -> DomainEvent:
    """The outbox event for an export that has just succeeded."""
    return DomainEvent(
        workspace_id=workspace_id,
        type=DomainEventType.EXPORT_FINISHED,
        payload=payload.model_dump(mode="json"),
    )
