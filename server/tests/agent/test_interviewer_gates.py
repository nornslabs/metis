"""The Interviewer's gates through the ``run_graph`` job: what the user and the database see.

Seam: the job function (as in ``test_interviewer.py``), on real Postgres and Redis with the
scripted LLM. The gate judge has its own script (``llm.judge``), so the specialist's replies and
the judge's verdicts never mix. Tests check the questions the user saw, the saved turns, the
run's status and the ``gate`` events.
"""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.core.events import RunEventType
from tests.agent.interview_helpers import ScriptedLLM, ask, finish, note
from tests.agent.run_job_helpers import events_of, job_ctx, keyed_run, run_job, run_row, statuses
from tests.agent.test_interviewer import FINDINGS, _brief, _questions, _turns

GENERIC = "What is the pain?"
SPECIFIC = "Which freelancers lose the most to late invoices?"
INFERABLE = "Is this a CRM?"
QUOTE = "A tiny CRM for freelancers"
PASS = "PASS"
PASS_BOTH = (PASS, PASS)


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


async def _gate_events(redis: Redis, run: Any) -> list[dict[str, Any]]:
    return [e.data for e in await events_of(redis, run) if e.type is RunEventType.GATE]


async def test_a_generic_question_is_rejected_and_the_revised_one_is_asked(
    redis: Redis, engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await keyed_run(engine)
    llm.add(ask(GENERIC, "problem"), ask(SPECIFIC, "problem"))
    llm.judge(PASS, "REJECT: Could be asked of any idea.", *PASS_BOTH)

    await run_job(ctx, run)

    assert await _questions(redis, run) == [SPECIFIC]
    assert "Could be asked of any idea" in llm.shown(1)
    assert [(g["gate"], g["decision"]) for g in await _gate_events(redis, run)] == [
        ("interview_input", "passed"),
        ("interview_output", "retried"),
        ("interview_input", "passed"),
        ("interview_output", "passed"),
    ]


async def test_a_question_answered_by_the_idea_text_is_skipped_and_saved_as_a_turn(
    redis: Redis, engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await keyed_run(engine)
    llm.add(ask(INFERABLE, "solution"), ask(SPECIFIC, "problem"))
    llm.judge(f'REJECT: answered: "{QUOTE}"', *PASS_BOTH)

    await run_job(ctx, run)

    assert await _questions(redis, run) == [SPECIFIC]
    assert await _turns(engine, run) == [
        ("solution", "noted", INFERABLE, QUOTE),
        ("problem", "asked", SPECIFIC, None),
    ]


async def test_a_quote_that_is_not_in_the_idea_is_a_plain_rejection(
    redis: Redis, engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await keyed_run(engine)
    llm.add(ask(INFERABLE, "solution"), ask(SPECIFIC, "problem"))
    llm.judge('REJECT: answered: "Sold to dentists only"', *PASS_BOTH)

    await run_job(ctx, run)

    assert await _questions(redis, run) == [SPECIFIC]
    assert await _turns(engine, run) == [("problem", "asked", SPECIFIC, None)]
    assert (await _gate_events(redis, run))[0]["decision"] == "retried"


async def test_a_near_duplicate_is_rejected_without_a_judge_call(
    redis: Redis, engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await keyed_run(engine)
    llm.add(
        note("problem", SPECIFIC, "Designers."),
        ask("Which freelancers lose the most to late invoices", "problem"),
        finish(**FINDINGS),
    )

    await run_job(ctx, run)

    assert llm.judge_bodies == []
    [event] = await _gate_events(redis, run)
    assert (event["gate"], event["decision"]) == ("interview_input", "retried")
    assert "repeats an earlier question" in event["reason"]
    assert await _questions(redis, run) == []


@pytest.mark.parametrize("verdict", ["maybe?", ""])
async def test_an_unreadable_judge_reply_lets_the_question_through(
    redis: Redis, engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, verdict: str
) -> None:
    run = await keyed_run(engine)
    llm.add(ask(SPECIFIC, "problem"))
    llm.judge(verdict, verdict)

    await run_job(ctx, run)

    assert await _questions(redis, run) == [SPECIFIC]


async def test_a_question_rejected_three_times_is_skipped_and_the_run_still_succeeds(
    redis: Redis, engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await keyed_run(engine)
    llm.add(
        ask(GENERIC, "problem"),
        ask(GENERIC, "problem"),
        ask(GENERIC, "problem"),
        finish(**FINDINGS),
    )
    reject = "REJECT: Could be asked of any idea."
    llm.judge(PASS, reject, PASS, reject, PASS, reject)

    await run_job(ctx, run)

    assert await _questions(redis, run) == []
    row = await run_row(engine, run)
    assert row.status == "succeeded"
    assert row.error is None
    assert await _brief(engine, run) is not None
    assert [
        g["decision"] for g in await _gate_events(redis, run) if g["gate"] == "interview_output"
    ] == [
        "retried",
        "retried",
        "skipped",
    ]
    assert statuses(await events_of(redis, run))[-1] == "succeeded"


async def test_a_resume_does_not_review_the_waiting_question_again(
    redis: Redis, engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await keyed_run(engine)
    llm.add(ask(SPECIFIC, "problem"), finish(**FINDINGS))

    await run_job(ctx, run)
    await run_job(ctx, run, resume="Designers.")

    assert len(llm.judge_bodies) == 2  # one input and one output review, none after the resume
    assert len(await _gate_events(redis, run)) == 2
