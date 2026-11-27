"""Interview rules: turns, coverage, the 8-question cap and the idea's brief.

Every function takes the caller's ``AsyncSession``, flushes but never commits and is scoped
to the workspace id as well as RLS. ``open_question`` and ``answer_question`` are safe to
call again with the same arguments: the Interviewer's node re-runs from its start when a
paused run resumes, and after a crash it can re-run even once the answer is saved.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import (
    IdeaNotFoundError,
    InterviewTurnNotFoundError,
    QuestionAlreadyOpenError,
)
from metis.core.logging import get_logger
from metis.modules.ideas import repo
from metis.modules.ideas.dto import (
    CHECKLIST,
    MAX_INTERVIEW_QUESTIONS,
    SKIP_ANSWER,
    STOP_ANSWERS,
    InterviewBrief,
    InterviewCoverage,
    InterviewEnd,
    InterviewFindings,
    InterviewTopic,
    InterviewTurn,
    InterviewTurnList,
    QuestionRefusal,
    TurnSource,
)

logger = get_logger(__name__)


class _AnswerKind(StrEnum):
    REAL = "real"
    SKIP = "skip"
    STOP = "stop"
    NONE = "none"


async def open_question(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    run_id: UUID,
    topic: InterviewTopic,
    question: str,
) -> InterviewTurn | QuestionRefusal:
    """Save a question before the run pauses on it, or say why it may not be asked.

    Re-run safe: the run's open question with the same text is returned as is (a re-run
    after resume), and so is the run's last asked question when it has the same text and
    is already answered (a re-run after a crash between saving the answer and the
    checkpoint). A different open question raises ``QuestionAlreadyOpenError``. Refused:
    after the user ended the interview, or once the run asked ``MAX_INTERVIEW_QUESTIONS``.
    """
    existing = await repo.interview.get_open_question(session, workspace_id, run_id)
    if existing is not None:
        return _same_question(existing, question)
    turns = await list_turns(session, workspace_id, idea_id)
    asked = [t for t in turns if t.run_id == run_id and t.source is TurnSource.ASKED]
    if asked and asked[-1].question == question:
        return asked[-1]
    refusal = _refusal(coverage_of(turns, run_id))
    if refusal is not None:
        logger.info("interview.question_refused", reason=refusal.value)
        return refusal
    row = await repo.interview.create_open_question_or_none(
        session, workspace_id, idea_id, run_id, topic=topic.value, question=question
    )
    if row is None:  # a parallel call opened one first
        raced = await repo.interview.get_open_question(session, workspace_id, run_id)
        if raced is None:
            raise QuestionAlreadyOpenError("Could not open the question.")
        return _same_question(raced, question)
    return InterviewTurn.model_validate(row)


async def answer_question(
    session: AsyncSession, workspace_id: UUID, turn_id: UUID, answer: str
) -> InterviewTurn:
    """Record the user's answer; an already answered turn is returned unchanged."""
    row = await repo.interview.answer(session, workspace_id, turn_id, answer)
    if row is None:
        row = await repo.interview.get(session, workspace_id, turn_id)
    if row is None:
        raise InterviewTurnNotFoundError()
    return InterviewTurn.model_validate(row)


async def save_interview_turn(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    run_id: UUID,
    topic: InterviewTopic,
    question: str,
    answer: str,
) -> InterviewTurn:
    """Record a topic the Interviewer took from the idea text or an earlier answer."""
    row = await repo.interview.create(
        session,
        workspace_id,
        idea_id,
        run_id,
        topic=topic.value,
        source=TurnSource.NOTED.value,
        question=question,
        answer=answer,
    )
    return InterviewTurn.model_validate(row)


async def list_turns(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID
) -> list[InterviewTurn]:
    """The idea's turns across all its runs, oldest first."""
    rows = await repo.interview.list_for_idea(session, workspace_id, idea_id)
    return [InterviewTurn.model_validate(row) for row in rows]


async def list_interview(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID
) -> InterviewTurnList:
    """The idea's turns, oldest first; an unknown, archived or foreign idea is not found."""
    if await repo.ideas.get(session, workspace_id, idea_id) is None:
        raise IdeaNotFoundError()
    return InterviewTurnList(items=tuple(await list_turns(session, workspace_id, idea_id)))


async def interview_coverage(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, run_id: UUID
) -> InterviewCoverage:
    """Which checklist topics the idea's turns answer, and how many questions ``run_id`` asked."""
    turns = await list_turns(session, workspace_id, idea_id)
    return coverage_of(turns, run_id)


def coverage_of(turns: Sequence[InterviewTurn], run_id: UUID) -> InterviewCoverage:
    """A topic is covered by a turn with a real answer: not empty, ``skip`` or a stop phrase."""
    answers = [(turn, _kind_of(turn.answer)) for turn in turns]
    answered = {turn.topic for turn, kind in answers if kind is _AnswerKind.REAL}
    skipped = {turn.topic for turn, kind in answers if kind is _AnswerKind.SKIP}
    in_run = [(turn, kind) for turn, kind in answers if turn.run_id == run_id]
    return InterviewCoverage(
        covered=tuple(t for t in CHECKLIST if t in answered),
        missing=tuple(t for t in CHECKLIST if t not in answered),
        skipped=tuple(t for t in CHECKLIST if t in skipped and t not in answered),
        questions_asked=sum(1 for turn, _ in in_run if turn.source is TurnSource.ASKED),
        user_ended=any(kind is _AnswerKind.STOP for _, kind in in_run),
    )


def question_progress(coverage: InterviewCoverage) -> tuple[int, int]:
    """``(index, total)`` for the question just opened.

    ``index`` counts the run's asked questions, this one included. Questions are free-form, so
    there is no estimate of how many remain: ``total`` is always ``MAX_INTERVIEW_QUESTIONS``.
    """
    return coverage.questions_asked, MAX_INTERVIEW_QUESTIONS


def end_reason(coverage: InterviewCoverage) -> InterviewEnd:
    """Why the interview ended, from its turns: the user, coverage, the cap, else the model."""
    if coverage.user_ended:
        return InterviewEnd.USER
    if coverage.complete:
        return InterviewEnd.COVERAGE
    if coverage.questions_asked >= MAX_INTERVIEW_QUESTIONS:
        return InterviewEnd.CAP
    return InterviewEnd.MODEL


async def finish_interview(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    run_id: UUID,
    findings: InterviewFindings,
) -> InterviewBrief:
    """Build the run's brief (the model's findings + coverage from the turns) and store it."""
    coverage = await interview_coverage(session, workspace_id, idea_id, run_id)
    brief = InterviewBrief(
        **findings.model_dump(),
        covered=coverage.covered,
        missing=coverage.missing,
        ended_by=end_reason(coverage),
        question_count=coverage.questions_asked,
    )
    await save_interview_brief(session, workspace_id, idea_id, brief)
    return brief


async def save_interview_brief(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, brief: InterviewBrief
) -> None:
    """Store ``brief`` on the idea, replacing an earlier one."""
    if not await repo.ideas.set_interview_brief(
        session, workspace_id, idea_id, brief.model_dump(mode="json")
    ):
        raise IdeaNotFoundError()
    logger.info("interview.brief_saved", idea_id=str(idea_id), ended_by=brief.ended_by.value)


async def get_interview_brief(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID
) -> InterviewBrief | None:
    """The idea's latest brief, ``None`` before its first interview finishes."""
    row = await repo.ideas.get(session, workspace_id, idea_id)
    if row is None:
        raise IdeaNotFoundError()
    if row.interview_brief is None:
        return None
    return InterviewBrief.model_validate(row.interview_brief)


def _same_question(row: object, question: str) -> InterviewTurn:
    turn = InterviewTurn.model_validate(row)
    if turn.question != question:
        raise QuestionAlreadyOpenError("The run already waits on another question.")
    return turn


def _refusal(coverage: InterviewCoverage) -> QuestionRefusal | None:
    if coverage.user_ended:
        return QuestionRefusal.USER_ENDED
    if coverage.questions_left == 0:
        return QuestionRefusal.CAP_REACHED
    return None


def _kind_of(answer: str | None) -> _AnswerKind:
    text = (answer or "").strip().rstrip(".!").strip().casefold().replace("\u2019", "'")
    if not text:
        return _AnswerKind.NONE
    if text == SKIP_ANSWER:
        return _AnswerKind.SKIP
    if text in STOP_ANSWERS:
        return _AnswerKind.STOP
    return _AnswerKind.REAL
