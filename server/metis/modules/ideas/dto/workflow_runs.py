"""Run DTOs: statuses, the run record and the reference crash recovery works from."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr

from metis.helpers.dto import FrozenModel
from metis.modules.ideas.dto.ideas import Stage


class RunStatus(StrEnum):
    """Where a run is. Moves go through ``helpers.run_transitions``."""

    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_USER = "awaiting_user"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunKind(StrEnum):
    PIPELINE = "pipeline"


class WorkflowRun(FrozenModel):
    """One run. ``error`` is ``{code, message}`` when failed; ``pending_interrupt`` is the
    question or approval the run waits on while ``awaiting_user``."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: UUID
    workspace_id: UUID
    idea_id: UUID
    kind: RunKind
    status: RunStatus
    started_at: datetime | None
    finished_at: datetime | None
    error: dict[str, Any] | None
    pending_interrupt: dict[str, Any] | None
    idempotency_key: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class RunRef(FrozenModel):
    """A run found without a workspace in scope: enough to enqueue its job."""

    run_id: UUID
    workspace_id: UUID


class RunView(FrozenModel):
    """A run as the API shows it: no workspace, kind or idempotency key. ``stage`` is the
    idea's current stage; ``pending_interrupt`` is set only while ``awaiting_user``."""

    id: UUID
    idea_id: UUID
    status: RunStatus
    stage: Stage
    pending_interrupt: dict[str, Any] | None
    error: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    version: int


class RunPage(FrozenModel):
    """One page of an idea's runs, newest first; ``next_cursor`` is ``None`` on the last page."""

    items: list[RunView]
    next_cursor: str | None


class ResumeBody(BaseModel):
    """The user's answer: text for a question, true/false for an approval."""

    value: StrictStr | StrictBool


class RunStarted(BaseModel):
    run_id: UUID


class RunCancelResult(BaseModel):
    """``status`` is ``cancelled`` when done at once, ``running`` while the worker stops it."""

    run_id: UUID
    status: RunStatus
