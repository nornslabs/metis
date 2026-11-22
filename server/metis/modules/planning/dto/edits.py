"""Request bodies of the plan edit routes."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from metis.helpers.dto import FrozenModel
from metis.modules.planning.dto._fields import Label, LongText, Name, TaskDescription, TaskTitle
from metis.modules.planning.dto.enums import MAX_LABELS, MAX_PHASE_OPS


class RenamePhase(FrozenModel):
    """Change the name, goal or exit criteria of a phase (what is given changes)."""

    op: Literal["rename"]
    phase_id: UUID
    name: Name | None = None
    goal: LongText | None = None
    exit_criteria: LongText | None = None


class ReorderPhases(FrozenModel):
    """Put the phases in this order; every phase of the plan must be listed once."""

    op: Literal["reorder"]
    phase_ids: tuple[UUID, ...]


class AddPhase(FrozenModel):
    """Add a phase at ``position`` (last by default); later phases move down."""

    op: Literal["add"]
    name: Name
    goal: LongText
    exit_criteria: LongText
    position: int | None = Field(default=None, ge=0)


class RemovePhase(FrozenModel):
    """Remove a phase; its tasks go to the end of ``move_tasks_to``."""

    op: Literal["remove"]
    phase_id: UUID
    move_tasks_to: UUID | None = None


PhaseOp = Annotated[RenamePhase | ReorderPhases | AddPhase | RemovePhase, Field(discriminator="op")]


class EditPhasesBody(FrozenModel):
    """Phase edits applied in order, all or none, on plan ``version``."""

    version: int = Field(ge=1)
    ops: tuple[PhaseOp, ...] = Field(min_length=1, max_length=MAX_PHASE_OPS)


class TaskPatch(FrozenModel):
    """The fields of a task to change. The estimate is checked by the plan rules."""

    title: TaskTitle | None = None
    description: TaskDescription | None = None
    estimate: int | None = None
    labels: tuple[Label, ...] | None = Field(default=None, max_length=MAX_LABELS)
    phase_id: UUID | None = None
    position: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _not_empty(self) -> TaskPatch:
        fields = (self.title, self.description, self.estimate, self.labels, self.phase_id)
        if self.position is None and all(value is None for value in fields):
            raise ValueError("give at least one field to change")
        return self


class EditTaskBody(TaskPatch):
    """A task patch made on plan ``version``."""

    version: int = Field(ge=1)
