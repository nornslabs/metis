"""Plan DTOs: what the Planner saves, and a stored plan with its phases, tasks and path."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from metis.helpers.dto import FrozenModel
from metis.modules.planning.dto._fields import (
    Label,
    LongText,
    Name,
    TaskDescription,
    TaskKey,
    TaskTitle,
)
from metis.modules.planning.dto.enums import MAX_LABELS, PlanStatus


class PhaseInput(FrozenModel):
    """One phase as the Planner saves it; its position is its place in the list."""

    name: Name
    goal: LongText
    exit_criteria: LongText


class TaskInput(FrozenModel):
    """One task as the Planner saves it.

    ``key`` names the task inside this plan input (deps and parents point at it);
    ``phase`` is the index of its phase in ``PlanInput.phases``. ``estimate`` is checked by the
    plan rules (Fibonacci up to 8), not here, so a bad value gets ``plan.invalid_plan``.
    """

    key: TaskKey
    phase: int
    title: TaskTitle
    description: TaskDescription = ""
    estimate: int
    labels: tuple[Label, ...] = Field(default=(), max_length=MAX_LABELS)
    parent_key: TaskKey | None = None


class DepInput(FrozenModel):
    """``task_key`` cannot start before ``blocked_by_key`` is done."""

    task_key: TaskKey
    blocked_by_key: TaskKey


class PlanInput(FrozenModel):
    """A whole plan, saved at once. Counts are limited by the plan rules, not here."""

    phases: tuple[PhaseInput, ...]
    tasks: tuple[TaskInput, ...]
    deps: tuple[DepInput, ...] = ()


class Task(FrozenModel):
    """A stored task; ``blocked_by`` lists the tasks that must finish first."""

    id: UUID
    position: int
    title: str
    description: str
    estimate: int
    labels: tuple[str, ...]
    parent_task_id: UUID | None
    blocked_by: tuple[UUID, ...]


class Phase(FrozenModel):
    """A stored phase with its tasks in order."""

    id: UUID
    position: int
    name: str
    goal: str
    exit_criteria: str
    tasks: tuple[Task, ...]


class CriticalPath(FrozenModel):
    """The dependency chain with the most points: its tasks in order, and the sum."""

    task_ids: tuple[UUID, ...]
    points: int


class Plan(FrozenModel):
    """A stored plan: phases → tasks → dependencies, and its critical path."""

    id: UUID
    idea_id: UUID
    spec_version_id: UUID
    status: PlanStatus
    version: int
    ready_at: datetime | None
    created_at: datetime
    updated_at: datetime
    phases: tuple[Phase, ...]
    critical_path: CriticalPath
