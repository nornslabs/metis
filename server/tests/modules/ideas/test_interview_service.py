"""Interview turns and the brief at the ideas module's public seam, as ``metis_app`` (RLS on).

The Interviewer's tools call these; the full interview flow is covered through the
``run_graph`` job in ``tests/agent/test_interviewer.py``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.core.db import set_workspace
from metis.core.errors import QuestionAlreadyOpenError
from metis.modules import ideas
from metis.modules.ideas import (
    MAX_INTERVIEW_QUESTIONS,
    InterviewBrief,
    InterviewEnd,
    InterviewTopic,
    QuestionRefusal,
)
from tests.agent.llm_helpers import make_run, workspace_without_key

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from uuid import UUID

Topic = InterviewTopic


@dataclass(frozen=True)
class Run:
    workspace_id: UUID
    idea_id: UUID
    run_id: UUID


async def _run(engine: AsyncEngine, sub: str = "ada") -> Run:
    workspace_id = await workspace_without_key(engine, sub)
    run_id = await make_run(engine, workspace_id)
    async with engine.connect() as conn:
        idea_id = await conn.scalar(
            text("SELECT idea_id FROM ideas.workflow_runs WHERE id = :id"), {"id": run_id}
        )
    return Run(workspace_id, idea_id, run_id)


@asynccontextmanager
async def _session(
    sessions: async_sessionmaker[AsyncSession], workspace_id: UUID
) -> AsyncGenerator[AsyncSession]:
    async with sessions() as session, session.begin():
        await set_workspace(session, workspace_id)
        yield session


async def _ask(
    sessions: async_sessionmaker[AsyncSession],
    run: Run,
    question: str,
    topic: Topic = Topic.PROBLEM,
) -> ideas.InterviewTurn | QuestionRefusal:
    async with _session(sessions, run.workspace_id) as s:
        return await ideas.open_question(
            s, run.workspace_id, run.idea_id, run.run_id, topic, question
        )


async def _answer(
    sessions: async_sessionmaker[AsyncSession], run: Run, turn_id: UUID, answer: str
) -> ideas.InterviewTurn:
    async with _session(sessions, run.workspace_id) as s:
        return await ideas.answer_question(s, run.workspace_id, turn_id, answer)


async def test_opening_the_same_question_again_returns_the_same_turn(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await _run(engine)

    first = await _ask(app_sessions, run, "Who feels this pain?")
    again = await _ask(app_sessions, run, "Who feels this pain?")

    assert isinstance(first, ideas.InterviewTurn) and isinstance(again, ideas.InterviewTurn)
    assert again.id == first.id
    assert again.answer is None


async def test_a_different_question_while_one_is_open_is_refused(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await _run(engine)
    await _ask(app_sessions, run, "Who feels this pain?")

    with pytest.raises(QuestionAlreadyOpenError):
        await _ask(app_sessions, run, "Who pays?", Topic.PAYMENT)


async def test_answering_twice_keeps_the_first_answer(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await _run(engine)
    turn = await _ask(app_sessions, run, "Who feels this pain?")
    assert isinstance(turn, ideas.InterviewTurn)

    await _answer(app_sessions, run, turn.id, "Freelancers.")
    again = await _answer(app_sessions, run, turn.id, "Agencies.")

    assert again.answer == "Freelancers."


async def test_the_last_question_again_after_its_answer_returns_the_answered_turn(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await _run(engine)
    turn = await _ask(app_sessions, run, "Who feels this pain?")
    assert isinstance(turn, ideas.InterviewTurn)
    await _answer(app_sessions, run, turn.id, "Freelancers.")

    again = await _ask(app_sessions, run, "Who feels this pain?")

    assert isinstance(again, ideas.InterviewTurn)
    assert again.id == turn.id
    assert again.answer == "Freelancers."


async def test_no_question_is_opened_after_the_user_ended_the_interview(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await _run(engine)
    turn = await _ask(app_sessions, run, "Who feels this pain?")
    assert isinstance(turn, ideas.InterviewTurn)
    await _answer(app_sessions, run, turn.id, "That’s enough!")

    refused = await _ask(app_sessions, run, "Who pays?", Topic.PAYMENT)

    assert refused is QuestionRefusal.USER_ENDED


async def test_a_run_asks_at_most_the_maximum_number_of_questions(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await _run(engine)
    for n in range(MAX_INTERVIEW_QUESTIONS):
        turn = await _ask(app_sessions, run, f"Question {n}?")
        assert isinstance(turn, ideas.InterviewTurn)
        await _answer(app_sessions, run, turn.id, "An answer.")

    over = await _ask(app_sessions, run, "One more?")

    assert over is QuestionRefusal.CAP_REACHED


async def test_coverage_counts_real_answers_and_notes_but_not_skips(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await _run(engine)
    problem = await _ask(app_sessions, run, "Why is it needed?")
    assert isinstance(problem, ideas.InterviewTurn)
    await _answer(app_sessions, run, problem.id, "Leads get lost.")
    payment = await _ask(app_sessions, run, "Who pays?", Topic.PAYMENT)
    assert isinstance(payment, ideas.InterviewTurn)
    await _answer(app_sessions, run, payment.id, "  Skip ")
    async with _session(app_sessions, run.workspace_id) as s:
        await ideas.save_interview_turn(
            s,
            run.workspace_id,
            run.idea_id,
            run.run_id,
            Topic.CUSTOMER,
            "Who is it for?",
            "Freelancers",
        )

    async with _session(app_sessions, run.workspace_id) as s:
        coverage = await ideas.interview_coverage(s, run.workspace_id, run.idea_id, run.run_id)

    assert coverage.covered == (Topic.PROBLEM, Topic.CUSTOMER)
    assert coverage.missing == (Topic.SOLUTION, Topic.PAYMENT, Topic.FEASIBILITY)
    assert coverage.questions_asked == 2


async def test_the_brief_is_stored_on_the_idea_and_replaced_by_a_later_one(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await _run(engine)
    first = InterviewBrief(
        problem="Leads get lost.",
        covered=(Topic.PROBLEM,),
        missing=(Topic.SOLUTION,),
        ended_by=InterviewEnd.USER,
        question_count=1,
    )
    second = first.model_copy(update={"ended_by": InterviewEnd.COVERAGE, "question_count": 3})

    async with _session(app_sessions, run.workspace_id) as s:
        assert await ideas.get_interview_brief(s, run.workspace_id, run.idea_id) is None
        await ideas.save_interview_brief(s, run.workspace_id, run.idea_id, first)
        await ideas.save_interview_brief(s, run.workspace_id, run.idea_id, second)
    async with _session(app_sessions, run.workspace_id) as s:
        stored = await ideas.get_interview_brief(s, run.workspace_id, run.idea_id)

    assert stored == second


async def test_turns_are_invisible_from_another_workspace(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    mine = await _run(engine, "ada")
    other = await _run(engine, "grace")
    await _ask(app_sessions, mine, "Why is it needed?")

    async with app_sessions() as session, session.begin():
        await set_workspace(session, other.workspace_id)
        visible = await session.scalar(text("SELECT count(*) FROM ideas.interview_turns"))
    async with _session(app_sessions, other.workspace_id) as s:
        turns = await ideas.list_turns(s, mine.workspace_id, mine.idea_id)

    assert visible == 0
    assert turns == []
