"""Domain events of the planning module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from metis.core.outbox import DomainEvent, DomainEventType
from metis.helpers.dto import FrozenModel

if TYPE_CHECKING:
    from uuid import UUID


class PlanReadyPayload(FrozenModel):
    """``PlanReady``: the plan the user accepted, ready to export."""

    idea_id: UUID
    plan_id: UUID
    spec_version_id: UUID
    version: int


def plan_ready(workspace_id: UUID, payload: PlanReadyPayload) -> DomainEvent:
    """The outbox event for a plan that has just become ready."""
    return DomainEvent(
        workspace_id=workspace_id,
        type=DomainEventType.PLAN_READY,
        payload=payload.model_dump(mode="json"),
    )
