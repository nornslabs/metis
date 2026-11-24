"""Phase edits: rename, reorder, add and remove, applied together on one plan version."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.logging import get_logger
from metis.modules.planning.dto import PhaseOp, Plan
from metis.modules.planning.helpers.layout import apply_phase_ops
from metis.modules.planning.service import layout, plans

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

logger = get_logger(__name__)


async def edit_phases(
    session: AsyncSession,
    workspace_id: UUID,
    plan_id: UUID,
    ops: Sequence[PhaseOp],
    version: int,
) -> Plan:
    """Apply ``ops`` in order to the draft plan at ``version``; all or none.

    Tasks keep their dependencies: a removed phase hands its tasks to another phase. A ready
    plan → ``PlanNotEditableError``; a stale ``version`` → ``PlanConflictError``; an op that
    breaks a rule → ``InvalidPlanError`` (the transaction must then be rolled back).
    """
    row = await plans.claim_draft(session, workspace_id, plan_id, version)
    before = await layout.load(session, workspace_id, plan_id)
    after = apply_phase_ops(before, ops)
    await layout.persist(session, workspace_id, plan_id, before, after)
    logger.info("plan.phases_edited", plan_id=str(plan_id), ops=len(ops), version=row.version)
    return await plans.load_plan(session, workspace_id, row)
