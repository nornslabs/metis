"""Run DTOs: statuses, the run record and the reference crash recovery works from."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    model_validator,
)

from metis.helpers.dto import FrozenModel
from metis.helpers.text import strip
from metis.modules.ideas.dto.ideas import MAX_RAW_TEXT_LENGTH, MIN_RAW_TEXT_LENGTH, Stage

MAX_CONTINUATION_PROMPT_LENGTH = 10_000
MAX_ACCEPTED = 5
ContinuationPrompt = Annotated[
    StrictStr,
    BeforeValidator(strip),
    Field(min_length=1, max_length=MAX_CONTINUATION_PROMPT_LENGTH),
]


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
    user_prompt: str | None = None
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
    user_prompt: str | None = None


class RunPage(FrozenModel):
    """One page of an idea's runs, newest first; ``next_cursor`` is ``None`` on the last page."""

    items: list[RunView]
    next_cursor: str | None


class AdviceDecision(StrEnum):
    """What the user chose after the Advisor's suggestions."""

    REVISE = "revise"
    CONTINUE = "continue"
    STOP = "stop"


class AdviceResume(FrozenModel):
    """The answer to an ``advice_decision`` interrupt.

    ``revise`` needs the idea's new text (the same bounds as an idea's text); the other
    decisions ignore ``revised_text``. ``accepted_suggestion_ids`` names the suggestions the
    user took; the Advisor ignores ids that are not its own.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: AdviceDecision
    revised_text: StrictStr | None = None
    accepted_suggestion_ids: tuple[UUID, ...] = Field(default=(), max_length=MAX_ACCEPTED)

    @model_validator(mode="after")
    def _check_revision(self) -> AdviceResume:
        if self.decision is not AdviceDecision.REVISE:
            return self
        text = (self.revised_text or "").strip()
        if not MIN_RAW_TEXT_LENGTH <= len(text) <= MAX_RAW_TEXT_LENGTH:
            raise ValueError(
                f"revised_text is {MIN_RAW_TEXT_LENGTH} to {MAX_RAW_TEXT_LENGTH} characters"
            )
        return self


class ResumeBody(BaseModel):
    """The user's answer: text for a question, true/false for an approval, or an advice decision."""

    value: StrictStr | StrictBool | AdviceResume


class StartRunBody(BaseModel):
    """Optional user message to continue the idea's existing chat."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: ContinuationPrompt | None = None


class RunStarted(BaseModel):
    run_id: UUID


class RunCancelResult(BaseModel):
    """``status`` is ``cancelled`` when done at once, ``running`` while the worker stops it."""

    run_id: UUID
    status: RunStatus
