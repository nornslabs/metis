"""The Interviewer through the ``run_graph`` job, as a run goes from submission to research.

Seam: the job function, called as Arq would (an answer is a second call with ``resume``,
as the runs API enqueues it), on real Postgres as ``metis_app``, real Redis and the real
checkpointer. The LLM is the only fake: a scripted OpenAI-compatible endpoint. Tests check
what the user and the database see: questions, run status, saved turns, the brief, events.
"""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.core.config import get_settings
from metis.core.events import RunEventType
from metis.helpers.ids import uuid7
from tests.agent.interview_helpers import ScriptedLLM, ask, finish, note, recall
from tests.agent.llm_helpers import usage_rows
from tests.agent.run_job_helpers import (
    QueuedRun,
    events_of,
    job_ctx,
    keyed_run,
    node_events,
    queued_run,
    run_job,
    run_row,
    statuses,
)

Q_PROBLEM = "What goes wrong for freelancers today?"
Q_SOLUTION = "Why would they switch from a spreadsheet?"
Q_PAYMENT = "Who pays, and how much?"
Q_FEASIBILITY = "Can you build and run it alone?"
A_PROBLEM = "Freelancers lose leads in their DMs."
FINDINGS = {
    "problem": "Leads get lost in DMs.",
    "target_customer": "Solo freelancers.",
    "current_alternatives": "Spreadsheets.",
    "willingness_to_pay": "$9 a month.",
    "feasibility": "One developer, a month.",
}
ALL_TOPICS = ["problem", "solution", "customer", "payment", "feasibility"]


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM()


@pytest.fixture
def ctx(
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
    llm: ScriptedLLM,
) -> dict[str, Any]:
    return job_ctx(redis, app_sessions, llm=llm)


async def _turns(engine: AsyncEngine, run: QueuedRun) -> list[tuple[str, str, str, str | None]]:
    """``(topic, source, question, answer)`` of the run's idea, oldest first."""
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT t.topic, t.source, t.question, t.answer FROM ideas.interview_turns t "
                "JOIN ideas.workflow_runs r ON r.idea_id = t.idea_id "
                "WHERE r.id = :run ORDER BY t.id"
            ),
            {"run": run.run_id},
        )
        return [tuple(row) for row in rows.all()]  # type: ignore[misc]


async def _brief(engine: AsyncEngine, run: QueuedRun) -> dict[str, Any] | None:
    async with engine.connect() as conn:
        return await conn.scalar(
            text(
                "SELECT i.interview_brief FROM ideas.ideas i "
                "JOIN ideas.workflow_runs r ON r.idea_id = i.id WHERE r.id = :run"
            ),
            {"run": run.run_id},
        )


async def _questions(redis: Redis, run: QueuedRun) -> list[str]:
    events = await events_of(redis, run)
    return [e.data["question"] for e in events if e.type is RunEventType.INTERRUPT]


async def _rerun_same_idea(engine: AsyncEngine, run: QueuedRun) -> QueuedRun:
    """A new queued run on ``run``'s idea (the first one must be finished)."""
    new_id = uuid7()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ideas.workflow_runs (id, workspace_id, idea_id) "
                "SELECT :new, workspace_id, idea_id FROM ideas.workflow_runs WHERE id = :old"
            ),
            {"new": new_id, "old": run.run_id},
        )
    return QueuedRun(new_id, run.workspace_id)


async def _answer_all(ctx: dict[str, Any], run: QueuedRun, answers: list[str]) -> None:
    for answer in answers:
        await run_job(ctx, run, resume=answer)


async def test_the_interview_asks_adapts_and_hands_over_to_research(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await keyed_run(engine)
    llm.add(recall(), ask(Q_PROBLEM, "problem"))
    llm.add(note("customer", "Who is it for?", "Freelancers."), ask(Q_SOLUTION, "solution"))
    llm.add(ask(Q_PAYMENT, "payment"))
    llm.add(ask(Q_FEASIBILITY, "feasibility"))
    llm.add(finish(**FINDINGS))

    await run_job(ctx, run)
    first = await run_row(engine, run)
    await _answer_all(ctx, run, [A_PROBLEM, "It reminds them.", "Them, $9.", "Yes."])

    assert first.status == "awaiting_user"
    assert first.pending_interrupt == {"type": "question", "question": Q_PROBLEM}
    assert await _questions(redis, run) == [Q_PROBLEM, Q_SOLUTION, Q_PAYMENT, Q_FEASIBILITY]
    assert A_PROBLEM in llm.shown(2)  # the model saw the answer before adapting
    assert await _turns(engine, run) == [
        ("problem", "asked", Q_PROBLEM, A_PROBLEM),
        ("customer", "noted", "Who is it for?", "Freelancers."),
        ("solution", "asked", Q_SOLUTION, "It reminds them."),
        ("payment", "asked", Q_PAYMENT, "Them, $9."),
        ("feasibility", "asked", Q_FEASIBILITY, "Yes."),
    ]
    brief = await _brief(engine, run)
    assert brief == {
        **FINDINGS,
        "covered": ALL_TOPICS,
        "missing": [],
        "ended_by": "coverage",
        "question_count": 4,
    }
    events = await events_of(redis, run)
    assert (await run_row(engine, run)).status == "succeeded"
    assert ("node_finished", "researcher") in node_events(events)
    assert statuses(events)[-1] == "succeeded"
    tool_calls = [e.data for e in events if e.type is RunEventType.TOOL_CALL]
    assert {"node": "interviewer", "name": "ask_user"} in tool_calls
    assert len(await usage_rows(engine, run.workspace_id)) == llm.calls


async def test_a_resume_never_saves_a_question_twice(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await keyed_run(engine)
    llm.add(ask(Q_PROBLEM, "problem"), ask(Q_PAYMENT, "payment"))

    await run_job(ctx, run)
    await run_job(ctx, run)  # a duplicate start job while the run waits: ignored
    await run_job(ctx, run, resume=A_PROBLEM)

    assert await _turns(engine, run) == [
        ("problem", "asked", Q_PROBLEM, A_PROBLEM),
        ("payment", "asked", Q_PAYMENT, None),
    ]


async def test_recovery_after_the_answer_was_saved_does_not_ask_again(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await keyed_run(engine)
    llm.add(ask(Q_PROBLEM, "problem"), ask(Q_PAYMENT, "payment"))
    await run_job(ctx, run)
    # The worker died after ``ask_user`` saved the answer but before the step's checkpoint:
    # the answer is in the database, the run is still ``running``, the checkpoint is at the pause.
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE ideas.interview_turns SET answer = :a WHERE question = :q"),
            {"a": A_PROBLEM, "q": Q_PROBLEM},
        )
        await conn.execute(
            text("UPDATE ideas.workflow_runs SET status = 'running' WHERE id = :id"),
            {"id": run.run_id},
        )

    await run_job(ctx, run)  # crash recovery: continue from the checkpoint, no resume value

    assert await _questions(redis, run) == [Q_PROBLEM, Q_PAYMENT]
    assert await _turns(engine, run) == [
        ("problem", "asked", Q_PROBLEM, A_PROBLEM),
        ("payment", "asked", Q_PAYMENT, None),
    ]
    assert A_PROBLEM in llm.shown(1)


async def test_the_interview_stops_after_eight_questions(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await keyed_run(engine)
    for n in range(9):
        llm.add(ask(f"Question {n}?", "other"))
    llm.add(finish(problem="Unclear."))

    await run_job(ctx, run)
    await _answer_all(ctx, run, [f"Answer {n}" for n in range(8)])

    assert len(await _questions(redis, run)) == 8
    assert "limit" in llm.shown(9).lower()  # the 9th ask was refused, not asked
    brief = await _brief(engine, run)
    assert brief is not None
    assert brief["ended_by"] == "cap"
    assert brief["question_count"] == 8
    assert brief["missing"] == ALL_TOPICS
    assert (await run_row(engine, run)).status == "succeeded"


async def test_the_user_can_end_the_interview(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await keyed_run(engine)
    llm.add(ask(Q_PROBLEM, "problem"))
    llm.add(ask(Q_PAYMENT, "payment"))
    llm.add(finish(problem="Leads get lost."))

    await run_job(ctx, run)
    await _answer_all(ctx, run, [A_PROBLEM, "That's enough"])

    brief = await _brief(engine, run)
    assert brief is not None
    assert brief["ended_by"] == "user"
    assert brief["covered"] == ["problem"]
    assert brief["missing"] == ["solution", "customer", "payment", "feasibility"]
    assert len(await _questions(redis, run)) == 2


async def test_skipped_topics_end_the_interview_as_missing(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await keyed_run(engine)
    for topic in ALL_TOPICS:
        llm.add(ask(f"About {topic}?", topic))
    llm.add(finish())

    await run_job(ctx, run)
    await _answer_all(ctx, run, ["Leads get lost.", "skip", "Freelancers.", "Skip", "Yes."])

    brief = await _brief(engine, run)
    assert brief is not None
    assert brief["ended_by"] == "coverage"
    assert brief["missing"] == ["solution", "payment"]


async def test_a_second_interview_recalls_the_first_and_asks_nothing_known(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await keyed_run(engine)
    llm.add(ask(Q_PROBLEM, "problem"), finish(problem="Leads get lost."))
    await run_job(ctx, run)
    await run_job(ctx, run, resume=A_PROBLEM)
    again = await _rerun_same_idea(engine, run)
    calls_before = llm.calls
    llm.add(recall(), finish(problem="Leads get lost."))

    await run_job(ctx, again)

    assert A_PROBLEM in llm.shown(calls_before + 1)  # recall_memory's result
    assert (await run_row(engine, again)).status == "succeeded"
    brief = await _brief(engine, again)
    assert brief is not None
    assert brief["covered"] == ["problem"]
    assert brief["question_count"] == 0


async def test_a_workspace_without_an_llm_key_fails_the_run(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await queued_run(engine)

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None
    assert row.error["code"] == "provider.not_configured"
    assert llm.calls == 0


async def test_the_stub_setting_keeps_every_specialist_a_stub(
    engine: AsyncEngine,
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
    llm: ScriptedLLM,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_STUB_SPECIALISTS", "true")
    get_settings.cache_clear()
    try:
        run = await queued_run(engine)  # no LLM key
        await run_job(job_ctx(redis, app_sessions, llm=llm), run)
    finally:
        monkeypatch.delenv("AGENT_STUB_SPECIALISTS")
        get_settings.cache_clear()

    assert (await run_row(engine, run)).status == "succeeded"
    assert llm.calls == 0
    assert await _brief(engine, run) is None
