"""Plans: save a whole plan, read it with its critical path, and mark it ready.

Every function takes the caller's ``AsyncSession``, flushes but never commits, and is scoped to
the workspace id as well as RLS. A plan is one per idea and spec version: it is a ``draft`` the
Planner replaces and members edit, and fixed once ``ready`` (``PlanReady`` is written once).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import (
    IdeaNotFoundError,
    PlanConflictError,
    PlanNotEditableError,
    PlanNotFoundError,
    SpecNotFoundError,
)
from metis.core.logging import get_logger
from metis.core.outbox import add_event
from metis.helpers.ids import uuid7
from metis.modules import ideas
from metis.modules.planning import repo
from metis.modules.planning.dto import Phase, Plan, PlanInput, PlanStatus, Task
from metis.modules.planning.events import PlanReadyPayload, plan_ready
from metis.modules.planning.helpers.critical_path import critical_path
from metis.modules.planning.helpers.validation import check_plan_input, check_stored_graph
from metis.modules.planning.models import PhaseRow, PlanRow, TaskDepRow, TaskRow

logger = get_logger(__name__)


async def save_plan(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    spec_version_id: UUID,
    data: PlanInput,
) -> Plan:
    """Store ``data`` as the plan for the idea's spec version, replacing its draft.

    The plan is checked first (``InvalidPlanError``); nothing is written when it fails. Unknown
    idea → ``IdeaNotFoundError``; a spec version of another idea → ``SpecNotFoundError``; a
    plan already ``ready`` for that version → ``PlanNotEditableError``.
    """
    check_plan_input(data)
    versions = await ideas.list_spec_versions(session, workspace_id, idea_id)
    if all(version.id != spec_version_id for version in versions.items):
        raise SpecNotFoundError("The idea has no such spec version")
    await repo.plans.lock_idea(session, idea_id)
    existing = await repo.plans.get_for_spec(session, workspace_id, idea_id, spec_version_id)
    if existing is None:
        row = await repo.plans.create(session, workspace_id, idea_id, spec_version_id)
    else:
        row = await _replace_draft(session, workspace_id, existing)
    await _insert_children(session, workspace_id, row.id, data)
    logger.info("plan.saved", plan_id=str(row.id), tasks=len(data.tasks), version=row.version)
    return await load_plan(session, workspace_id, row)


async def get_plan(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    spec_version_id: UUID | None = None,
) -> Plan:
    """The plan for ``spec_version_id``, or the idea's newest plan; none → ``PlanNotFoundError``."""
    await ideas.get_idea(session, workspace_id, idea_id)
    if spec_version_id is None:
        row = await repo.plans.latest_for_idea(session, workspace_id, idea_id)
    else:
        row = await repo.plans.get_for_spec(session, workspace_id, idea_id, spec_version_id)
    if row is None:
        raise PlanNotFoundError("The idea has no plan yet")
    return await load_plan(session, workspace_id, row)


async def mark_ready(session: AsyncSession, workspace_id: UUID, plan_id: UUID) -> Plan:
    """Fix the plan and write ``PlanReady``; a plan already ready is returned as it is.

    The stored graph is checked again, so a plan that breaks a rule cannot be marked ready.
    """
    row = await find_row(session, workspace_id, plan_id)
    plan = await load_plan(session, workspace_id, row)
    if row.status == PlanStatus.READY:
        return plan
    tasks = [task for phase in plan.phases for task in phase.tasks]
    check_stored_graph(
        [task.id for task in tasks],
        {t.id: t.parent_task_id for t in tasks if t.parent_task_id is not None},
        [(blocker, task.id) for task in tasks for blocker in task.blocked_by],
    )
    updated = await repo.plans.mark_ready(session, workspace_id, plan_id)
    if updated is None:  # another request made it ready first, and wrote the event
        return await load_plan(
            session, workspace_id, await find_row(session, workspace_id, plan_id)
        )
    add_event(
        session,
        plan_ready(
            workspace_id,
            PlanReadyPayload(
                idea_id=updated.idea_id,
                plan_id=updated.id,
                spec_version_id=updated.spec_version_id,
                version=updated.version,
            ),
        ),
    )
    logger.info("plan.ready", plan_id=str(plan_id), version=updated.version)
    return await load_plan(session, workspace_id, updated)


async def find_row(session: AsyncSession, workspace_id: UUID, plan_id: UUID) -> PlanRow:
    """The plan row; unknown, foreign or on an archived idea → ``PlanNotFoundError``."""
    row = await repo.plans.get(session, workspace_id, plan_id)
    if row is None:
        raise PlanNotFoundError("Plan not found")
    try:
        await ideas.get_idea(session, workspace_id, row.idea_id)
    except IdeaNotFoundError:
        raise PlanNotFoundError("Plan not found") from None
    return row


async def claim_draft(
    session: AsyncSession, workspace_id: UUID, plan_id: UUID, version: int
) -> PlanRow:
    """Take the draft plan for one edit: it must be at ``version`` and not ready.

    Returns the plan at its new version. A ready plan → ``PlanNotEditableError``; an edit made
    on an old version → ``PlanConflictError``.
    """
    row = await find_row(session, workspace_id, plan_id)
    if row.status != PlanStatus.DRAFT:
        raise PlanNotEditableError("A plan that is ready can no longer be changed")
    claimed = await repo.plans.claim_version(session, workspace_id, plan_id, version)
    if claimed is None:
        raise PlanConflictError("The plan changed since you loaded it; reload and try again")
    return claimed


async def load_plan(session: AsyncSession, workspace_id: UUID, row: PlanRow) -> Plan:
    """The plan with phases → tasks → dependencies in order, and its critical path."""
    phases = await repo.phases.list_for_plan(session, workspace_id, row.id)
    tasks = await repo.tasks.list_for_plan(session, workspace_id, row.id)
    deps = await repo.task_deps.list_for_plan(session, workspace_id, row.id)
    views = _phase_views(phases, tasks, deps)
    return Plan(
        id=row.id,
        idea_id=row.idea_id,
        spec_version_id=row.spec_version_id,
        status=PlanStatus(row.status),
        version=row.version,
        ready_at=row.ready_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        phases=views,
        critical_path=critical_path(views),
    )


async def _replace_draft(session: AsyncSession, workspace_id: UUID, existing: PlanRow) -> PlanRow:
    if existing.status != PlanStatus.DRAFT:
        raise PlanNotEditableError("A plan that is ready can no longer be replaced")
    row = await repo.plans.claim_version(session, workspace_id, existing.id, existing.version)
    if row is None:  # an edit or a ready call got in between the read and the claim
        current = await find_row(session, workspace_id, existing.id)
        if current.status != PlanStatus.DRAFT:
            raise PlanNotEditableError("A plan that is ready can no longer be replaced")
        raise PlanConflictError("The plan changed while it was being replaced; try again")
    await repo.task_deps.remove_for_plan(session, workspace_id, row.id)
    await repo.tasks.remove_for_plan(session, workspace_id, row.id)
    await repo.phases.remove_for_plan(session, workspace_id, row.id)
    return row


async def _insert_children(
    session: AsyncSession, workspace_id: UUID, plan_id: UUID, data: PlanInput
) -> None:
    phase_ids = [uuid7() for _ in data.phases]
    await repo.phases.create_many(
        session,
        workspace_id,
        plan_id,
        [
            {
                "id": phase_ids[index],
                "position": index,
                "name": phase.name,
                "goal": phase.goal,
                "exit_criteria": phase.exit_criteria,
            }
            for index, phase in enumerate(data.phases)
        ],
    )
    task_ids = {task.key: uuid7() for task in data.tasks}
    next_position: dict[int, int] = defaultdict(int)
    rows: list[dict[str, Any]] = []
    for task in data.tasks:
        rows.append(
            {
                "id": task_ids[task.key],
                "phase_id": phase_ids[task.phase],
                "position": next_position[task.phase],
                "title": task.title,
                "description": task.description,
                "estimate": task.estimate,
                "labels": list(task.labels),
                "parent_task_id": None if task.parent_key is None else task_ids[task.parent_key],
            }
        )
        next_position[task.phase] += 1
    await repo.tasks.create_many(session, workspace_id, plan_id, rows)
    await repo.task_deps.create_many(
        session,
        workspace_id,
        plan_id,
        [(task_ids[d.task_key], task_ids[d.blocked_by_key]) for d in data.deps],
    )


def _phase_views(
    phases: list[PhaseRow], tasks: list[TaskRow], deps: list[TaskDepRow]
) -> tuple[Phase, ...]:
    phase_position = {phase.id: phase.position for phase in phases}
    place = {task.id: (phase_position[task.phase_id], task.position) for task in tasks}
    blockers: dict[UUID, list[UUID]] = defaultdict(list)
    for dep in deps:
        blockers[dep.task_id].append(dep.blocked_by_task_id)
    by_phase: dict[UUID, list[TaskRow]] = defaultdict(list)
    for task in tasks:
        by_phase[task.phase_id].append(task)
    return tuple(
        Phase(
            id=phase.id,
            position=phase.position,
            name=phase.name,
            goal=phase.goal,
            exit_criteria=phase.exit_criteria,
            tasks=tuple(
                Task(
                    id=task.id,
                    position=task.position,
                    title=task.title,
                    description=task.description,
                    estimate=task.estimate,
                    labels=tuple(task.labels),
                    parent_task_id=task.parent_task_id,
                    blocked_by=tuple(sorted(blockers[task.id], key=place.__getitem__)),
                )
                for task in sorted(by_phase[phase.id], key=lambda t: t.position)
            ),
        )
        for phase in phases
    )
