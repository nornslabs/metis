"""Run DTOs: statuses, the run record and the reference crash recovery works from."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any

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

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

MAX_CONTINUATION_PROMPT_LENGTH = 10_000
MAX_ACCEPTED = 5
MAX_ANSWER_OPTIONS = 5  # the most options a question offers (``agent/tools/question_options``)
# The planning module's phase limits (``ideas`` cannot import ``planning``); the Planner checks
# the reviewed list against planning's own rules again when it saves the plan.
MAX_REVIEWED_PHASES = 12
MAX_PHASE_NAME_LENGTH = 120
MAX_PHASE_TEXT_LENGTH = 1_000
PhaseName = Annotated[
    StrictStr,
    BeforeValidator(strip),
    Field(min_length=1, max_length=MAX_PHASE_NAME_LENGTH),
]
PhaseText = Annotated[
    StrictStr,
    BeforeValidator(strip),
    Field(min_length=1, max_length=MAX_PHASE_TEXT_LENGTH),
]
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
    RESCORE = "rescore"
    MARKET_RECHECK = "market_recheck"


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
    kind: RunKind
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


class ReviewedPhase(FrozenModel):
    """One phase as the user left it at the ``phase_review`` interrupt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: PhaseName
    goal: PhaseText
    exit_criteria: PhaseText


class PhaseReviewResume(FrozenModel):
    """The answer to a ``phase_review`` interrupt: the phases to write tasks for, in order.

    Approving the proposal as it is means sending the proposed list back.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    phases: tuple[ReviewedPhase, ...] = Field(min_length=1, max_length=MAX_REVIEWED_PHASES)


class QuestionAnswer(FrozenModel):
    """The answer to a ``question`` interrupt that offered options.

    Exactly one of ``option_ids`` (ids from the pending question's options) or ``text`` (free
    text) is given; the check against the pending interrupt is in ``check_resume_value``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    option_ids: tuple[StrictStr, ...] = Field(default=(), max_length=MAX_ANSWER_OPTIONS)
    text: StrictStr | None = None


class TeamChoice(FrozenModel):
    """The answer to a ``choose_team`` interrupt: the id of one of the teams it offered."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    team_id: StrictStr = Field(min_length=1, max_length=200)


class ExportApprovalResume(FrozenModel):
    """The answer to an ``export_approval`` interrupt. A bare true/false is not accepted: the
    export must be approved or declined by name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approved: StrictBool


ResumeValue = (
    StrictStr
    | StrictBool
    | AdviceResume
    | PhaseReviewResume
    | TeamChoice
    | ExportApprovalResume
    | QuestionAnswer
)


class ResumeBody(BaseModel):
    """The user's answer: text or options (question), true/false (approval) or a decision."""

    value: ResumeValue


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
