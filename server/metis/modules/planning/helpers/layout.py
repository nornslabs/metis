"""A plan's layout (phases in order, task ids in order per phase) and the edits that change it.

Pure and immutable: every edit returns a new ``Layout``. The service loads a layout, applies the
edits, and writes back the difference.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from uuid import UUID

from metis.core.errors import PlanNotFoundError
from metis.helpers.ids import uuid7
from metis.modules.planning.dto import (
    MAX_PHASES,
    AddPhase,
    InvalidPlanReason,
    PhaseOp,
    RemovePhase,
    RenamePhase,
    ReorderPhases,
)
from metis.modules.planning.helpers.validation import refuse


@dataclass(frozen=True)
class PhaseDraft:
    """The editable text of a phase."""

    id: UUID
    name: str
    goal: str
    exit_criteria: str


@dataclass(frozen=True)
class Layout:
    """Phases in order, and for each phase the ids of its tasks in order."""

    phases: tuple[PhaseDraft, ...]
    tasks: Mapping[UUID, tuple[UUID, ...]]

    def phase_ids(self) -> tuple[UUID, ...]:
        return tuple(phase.id for phase in self.phases)


def apply_phase_ops(layout: Layout, ops: Sequence[PhaseOp]) -> Layout:
    """Apply the ops in order; the first one that fails refuses the whole list."""
    for op in ops:
        layout = _apply(layout, op)
    return layout


def move_task(layout: Layout, task_id: UUID, phase_id: UUID | None, position: int | None) -> Layout:
    """Put a task in ``phase_id`` (its own phase by default) at ``position``.

    Without a position the task stays where it is in its own phase and goes last in another.
    """
    source = next((pid for pid, ids in layout.tasks.items() if task_id in ids), None)
    if source is None:
        raise PlanNotFoundError("Task not found", meta={"task_id": str(task_id)})
    target = source if phase_id is None else phase_id
    if target not in layout.phase_ids():
        raise PlanNotFoundError("Phase not found", meta={"phase_id": str(target)})
    original = layout.tasks[source]
    remaining = {pid: tuple(t for t in ids if t != task_id) for pid, ids in layout.tasks.items()}
    if position is None:
        position = original.index(task_id) if target == source else len(remaining[target])
    if position > len(remaining[target]):
        refuse(
            InvalidPlanReason.BAD_POSITION,
            f"Position {position} is past the end of the phase.",
            [task_id],
        )
    ids = remaining[target]
    remaining[target] = (*ids[:position], task_id, *ids[position:])
    return replace(layout, tasks=remaining)


def _apply(layout: Layout, op: PhaseOp) -> Layout:
    match op:
        case RenamePhase():
            return _rename(layout, op)
        case ReorderPhases():
            return _reorder(layout, op)
        case AddPhase():
            return _add(layout, op)
        case RemovePhase():
            return _remove(layout, op)


def _find(layout: Layout, phase_id: UUID) -> PhaseDraft:
    for phase in layout.phases:
        if phase.id == phase_id:
            return phase
    raise PlanNotFoundError("Phase not found", meta={"phase_id": str(phase_id)})


def _rename(layout: Layout, op: RenamePhase) -> Layout:
    current = _find(layout, op.phase_id)
    renamed = replace(
        current,
        name=current.name if op.name is None else op.name,
        goal=current.goal if op.goal is None else op.goal,
        exit_criteria=current.exit_criteria if op.exit_criteria is None else op.exit_criteria,
    )
    phases = tuple(renamed if p.id == op.phase_id else p for p in layout.phases)
    return replace(layout, phases=phases)


def _reorder(layout: Layout, op: ReorderPhases) -> Layout:
    if sorted(op.phase_ids) != sorted(layout.phase_ids()):
        refuse(
            InvalidPlanReason.BAD_OPERATION,
            "A reorder must list every phase of the plan exactly once.",
        )
    by_id = {phase.id: phase for phase in layout.phases}
    return replace(layout, phases=tuple(by_id[pid] for pid in op.phase_ids))


def _add(layout: Layout, op: AddPhase) -> Layout:
    if len(layout.phases) >= MAX_PHASES:
        refuse(InvalidPlanReason.LIMIT_EXCEEDED, f"A plan has at most {MAX_PHASES} phases.")
    position = len(layout.phases) if op.position is None else op.position
    if position > len(layout.phases):
        refuse(InvalidPlanReason.BAD_POSITION, f"Position {position} is past the last phase.")
    phase = PhaseDraft(uuid7(), op.name, op.goal, op.exit_criteria)
    phases = (*layout.phases[:position], phase, *layout.phases[position:])
    return replace(layout, phases=phases, tasks={**layout.tasks, phase.id: ()})


def _remove(layout: Layout, op: RemovePhase) -> Layout:
    _find(layout, op.phase_id)
    if len(layout.phases) == 1:
        refuse(InvalidPlanReason.BAD_OPERATION, "A plan keeps at least one phase.")
    moving = layout.tasks[op.phase_id]
    tasks = {pid: ids for pid, ids in layout.tasks.items() if pid != op.phase_id}
    if moving:
        if op.move_tasks_to is None:
            refuse(
                InvalidPlanReason.BAD_OPERATION,
                "This phase has tasks; say which phase should take them (move_tasks_to).",
            )
        if op.move_tasks_to == op.phase_id:
            refuse(InvalidPlanReason.BAD_OPERATION, "Tasks cannot move to the removed phase.")
        _find(layout, op.move_tasks_to)
        tasks[op.move_tasks_to] = (*tasks[op.move_tasks_to], *moving)
    phases = tuple(p for p in layout.phases if p.id != op.phase_id)
    return replace(layout, phases=phases, tasks=tasks)
