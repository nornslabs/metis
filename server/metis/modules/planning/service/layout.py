"""Load a plan's layout and write an edited one back (only what changed)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from metis.modules.planning import repo
from metis.modules.planning.helpers.layout import Layout, PhaseDraft

if TYPE_CHECKING:
    from uuid import UUID


async def load(session: AsyncSession, workspace_id: UUID, plan_id: UUID) -> Layout:
    """The plan's phases in order, and each phase's task ids in order."""
    phases = await repo.phases.list_for_plan(session, workspace_id, plan_id)
    tasks = await repo.tasks.list_for_plan(session, workspace_id, plan_id)
    ordered: dict[UUID, list[UUID]] = {phase.id: [] for phase in phases}
    for task in tasks:  # the repo returns tasks by position
        ordered[task.phase_id].append(task.id)
    return Layout(
        phases=tuple(PhaseDraft(p.id, p.name, p.goal, p.exit_criteria) for p in phases),
        tasks={phase_id: tuple(ids) for phase_id, ids in ordered.items()},
    )


async def persist(
    session: AsyncSession, workspace_id: UUID, plan_id: UUID, old: Layout, new: Layout
) -> None:
    """Write the difference between two layouts of one plan.

    New phases first, then moved tasks, then changed phases, then removed phases, so no row
    ever points at a phase that is missing. Positions are checked at commit.
    """
    old_phases = {phase.id: (index, phase) for index, phase in enumerate(old.phases)}
    added = [
        {
            "id": phase.id,
            "position": index,
            "name": phase.name,
            "goal": phase.goal,
            "exit_criteria": phase.exit_criteria,
        }
        for index, phase in enumerate(new.phases)
        if phase.id not in old_phases
    ]
    await repo.phases.create_many(session, workspace_id, plan_id, added)
    await _write_tasks(session, workspace_id, old, new)
    for index, phase in enumerate(new.phases):
        before = old_phases.get(phase.id)
        if before is not None and before != (index, phase):
            await repo.phases.update_one(
                session,
                workspace_id,
                phase.id,
                {
                    "position": index,
                    "name": phase.name,
                    "goal": phase.goal,
                    "exit_criteria": phase.exit_criteria,
                },
            )
    removed = [phase_id for phase_id in old_phases if phase_id not in new.phase_ids()]
    await repo.phases.remove_many(session, workspace_id, removed)


async def _write_tasks(session: AsyncSession, workspace_id: UUID, old: Layout, new: Layout) -> None:
    before = {
        task_id: (phase_id, position)
        for phase_id, ids in old.tasks.items()
        for position, task_id in enumerate(ids)
    }
    for phase_id, ids in new.tasks.items():
        for position, task_id in enumerate(ids):
            if before.get(task_id) != (phase_id, position):
                await repo.tasks.update_one(
                    session, workspace_id, task_id, {"phase_id": phase_id, "position": position}
                )
