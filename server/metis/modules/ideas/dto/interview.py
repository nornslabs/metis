"""Interview DTOs: topics, turns, coverage and the brief the Interviewer leaves on the idea."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from pydantic import Field

from metis.helpers.dto import FrozenModel

MAX_INTERVIEW_QUESTIONS = 8
SKIP_ANSWER = "skip"
# Answers that end the interview (compared casefolded, trimmed, without end punctuation).
STOP_ANSWERS = frozenset({"that's enough", "thats enough", "enough", "stop"})
MAX_BRIEF_FIELD_LENGTH = 2_000


class InterviewTopic(StrEnum):
    """What a turn is about. The first five are the coverage checklist; ``other`` is not."""

    PROBLEM = "problem"
    SOLUTION = "solution"
    CUSTOMER = "customer"
    PAYMENT = "payment"
    FEASIBILITY = "feasibility"
    OTHER = "other"


CHECKLIST: tuple[InterviewTopic, ...] = (
    InterviewTopic.PROBLEM,
    InterviewTopic.SOLUTION,
    InterviewTopic.CUSTOMER,
    InterviewTopic.PAYMENT,
    InterviewTopic.FEASIBILITY,
)

# What each checklist topic means, for the prompt-facing tool descriptions.
TOPIC_MEANING: MappingProxyType[InterviewTopic, str] = MappingProxyType(
    {
        InterviewTopic.PROBLEM: "why the idea is needed: the pain and who feels it",
        InterviewTopic.SOLUTION: "why it works, and what people use today instead",
        InterviewTopic.CUSTOMER: "the target user or buyer",
        InterviewTopic.PAYMENT: "who pays, and how much they would pay",
        InterviewTopic.FEASIBILITY: "whether it can be built and run with the founder's means",
        InterviewTopic.OTHER: "anything outside the checklist",
    }
)


class TurnSource(StrEnum):
    """``asked``: a question the user saw. ``noted``: taken from the idea or an earlier answer."""

    ASKED = "asked"
    NOTED = "noted"


class InterviewEnd(StrEnum):
    """Why an interview ended. ``model``: the model stopped without calling its finish tool."""

    COVERAGE = "coverage"
    USER = "user"
    CAP = "cap"
    MODEL = "model"


class InterviewTurn(FrozenModel):
    """One turn. ``answer`` is ``None`` while an asked question waits for the user."""

    id: UUID
    idea_id: UUID
    run_id: UUID
    topic: InterviewTopic
    source: TurnSource
    question: str
    answer: str | None


class InterviewTurnList(FrozenModel):
    """An idea's interview turns across all its runs, oldest first."""

    items: tuple[InterviewTurn, ...]


class InterviewCoverage(FrozenModel):
    """Where an idea's interview stands for one run.

    ``covered``: checklist topics with a real answer. ``missing``: the rest. ``skipped``:
    missing topics the user answered ``skip``. ``questions_asked`` and ``user_ended``
    (the user answered "That's enough") are about the run only.
    """

    covered: tuple[InterviewTopic, ...]
    missing: tuple[InterviewTopic, ...]
    skipped: tuple[InterviewTopic, ...]
    questions_asked: int
    user_ended: bool

    @property
    def complete(self) -> bool:
        """Every checklist topic is answered or skipped."""
        return set(self.missing) <= set(self.skipped)

    @property
    def questions_left(self) -> int:
        """Questions the run may still ask under ``MAX_INTERVIEW_QUESTIONS``."""
        return max(0, MAX_INTERVIEW_QUESTIONS - self.questions_asked)


class QuestionRefusal(StrEnum):
    """Why ``open_question`` did not open a question."""

    CAP_REACHED = "cap_reached"
    USER_ENDED = "user_ended"


BriefText = str | None


class InterviewFindings(FrozenModel):
    """The part of the brief the model writes: one short line per topic, ``None`` if unknown."""

    problem: BriefText = Field(default=None, max_length=MAX_BRIEF_FIELD_LENGTH)
    target_customer: BriefText = Field(default=None, max_length=MAX_BRIEF_FIELD_LENGTH)
    current_alternatives: BriefText = Field(default=None, max_length=MAX_BRIEF_FIELD_LENGTH)
    willingness_to_pay: BriefText = Field(default=None, max_length=MAX_BRIEF_FIELD_LENGTH)
    feasibility: BriefText = Field(default=None, max_length=MAX_BRIEF_FIELD_LENGTH)


class InterviewBrief(InterviewFindings):
    """The interview's outcome, stored on the idea. Coverage comes from the turns, not the model."""

    covered: tuple[InterviewTopic, ...]
    missing: tuple[InterviewTopic, ...]
    ended_by: InterviewEnd
    question_count: int = Field(ge=0)
