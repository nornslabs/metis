"""Task edits: change a task's text, estimate, labels or place."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import PlanNotFoundError
from metis.core.logging import get_logger
from metis.modules.planning import repo
from metis.modules.planning.dto import Plan, TaskPatch
from metis.modules.planning.helpers.layout import move_task
from metis.modules.planning.helpers.validation import check_estimate
from metis.modules.planning.service import layout, plans

if TYPE_CHECKING:
    from uuid import UUID

logger = get_logger(__name__)


async def edit_task(
    session: AsyncSession,
    workspace_id: UUID,
    plan_id: UUID,
    task_id: UUID,
    patch: TaskPatch,
    version: int,
) -> Plan:
    """Change the fields given on one task of the draft plan at ``version``.

    A new ``phase_id`` or ``position`` moves the task; its dependencies stay. Same errors as
    ``edit_phases``, plus ``PlanNotFoundError`` for an unknown task or phase and
    ``InvalidPlanError`` for a bad estimate or position.
    """
    row = await plans.claim_draft(session, workspace_id, plan_id, version)
    task = await repo.tasks.get(session, workspace_id, plan_id, task_id)
    if task is None:
        raise PlanNotFoundError("Task not found", meta={"task_id": str(task_id)})
    if patch.estimate is not None:
        check_estimate(task_id, patch.estimate)
    fields = _changed_fields(patch)
    if fields:
        await repo.tasks.update_one(session, workspace_id, task_id, fields)
    if patch.phase_id is not None or patch.position is not None:
        before = await layout.load(session, workspace_id, plan_id)
        after = move_task(before, task_id, patch.phase_id, patch.position)
        await layout.persist(session, workspace_id, plan_id, before, after)
    logger.info("plan.task_edited", plan_id=str(plan_id), task_id=str(task_id))
    return await plans.load_plan(session, workspace_id, row)


def _changed_fields(patch: TaskPatch) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if patch.title is not None:
        fields["title"] = patch.title
    if patch.description is not None:
        fields["description"] = patch.description
    if patch.estimate is not None:
        fields["estimate"] = patch.estimate
    if patch.labels is not None:
        fields["labels"] = list(patch.labels)
    return fields
