"""Plan routes: ``GET /v1/ideas/{id}/plan`` and the edits under ``/v1/plans/{id}``.

Any workspace member may use them. No route saves a plan: the Planner does that through the
module's service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from metis.core.db import SessionDep
from metis.modules.identity import CurrentWorkspaceDep
from metis.modules.planning import service
from metis.modules.planning.dto import EditPhasesBody, EditTaskBody, Plan

if TYPE_CHECKING:
    from uuid import UUID

idea_router = APIRouter(prefix="/ideas")
router = APIRouter(prefix="/plans")


@idea_router.get("/{idea_id}/plan", response_model=Plan)
async def get_plan(
    session: SessionDep,
    workspace: CurrentWorkspaceDep,
    idea_id: UUID,
    spec_version_id: UUID | None = None,
) -> Plan:
    """The idea's newest plan (or the one for ``spec_version_id``) with its critical path."""
    return await service.plans.get_plan(session, workspace.workspace.id, idea_id, spec_version_id)


@router.patch("/{plan_id}/phases", response_model=Plan)
async def edit_phases(
    session: SessionDep, workspace: CurrentWorkspaceDep, plan_id: UUID, body: EditPhasesBody
) -> Plan:
    """Rename, reorder, add or remove phases on plan ``version``; 409 when it is stale."""
    return await service.phases.edit_phases(
        session, workspace.workspace.id, plan_id, body.ops, body.version
    )


@router.patch("/{plan_id}/tasks/{task_id}", response_model=Plan)
async def edit_task(
    session: SessionDep,
    workspace: CurrentWorkspaceDep,
    plan_id: UUID,
    task_id: UUID,
    body: EditTaskBody,
) -> Plan:
    """Change one task (text, estimate, labels, phase, position) on plan ``version``."""
    return await service.tasks.edit_task(
        session, workspace.workspace.id, plan_id, task_id, body, body.version
    )


@router.post("/{plan_id}/ready", response_model=Plan)
async def mark_ready(session: SessionDep, workspace: CurrentWorkspaceDep, plan_id: UUID) -> Plan:
    """Fix the plan and emit ``PlanReady`` (once; asking again returns the plan unchanged)."""
    return await service.plans.mark_ready(session, workspace.workspace.id, plan_id)
