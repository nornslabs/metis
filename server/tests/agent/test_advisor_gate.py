"""The Advisor's output gate through the ``run_graph`` job: what the user and the database see.

Seam: the job function (as in ``test_advisor.py``), on real Postgres and Redis with the scripted
LLM. The gate judge has its own script (``llm.judge``), so the Advisor's replies and the judge's
verdicts never mix. Tests check the saved suggestions, the run's status and error, the
``advice_decision`` interrupt and the ``gate`` events.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.core.events import RunEventType
from tests.agent.interview_helpers import Reply, ScriptedLLM
from tests.agent.run_job_helpers import events_of, job_ctx, run_job, run_row
from tests.agent.test_advisor import (
    _advised_run,
    _pending,
    _suggestions,
    finish_advice,
    suggest,
    three,
)
from tests.modules.identity.fake_exa_mcp import FakeExaMcp

GENERIC = "REJECT: This could be given to any idea."
INVENTED = "https://invented.example.com/page"


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM()


@pytest_asyncio.fixture
async def exa() -> AsyncIterator[FakeExaMcp]:
    async with FakeExaMcp().running() as fake:
        yield fake


@pytest.fixture
def ctx(
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
    llm: ScriptedLLM,
    exa: FakeExaMcp,
) -> dict[str, Any]:
    def make_client(headers: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=exa.transport(), headers=dict(headers))

    return job_ctx(redis, app_sessions, llm=llm, exa=make_client, score=True, advise=True)


async def _gate_events(redis: Redis, run: Any) -> list[tuple[str, str]]:
    events = await events_of(redis, run)
    return [
        (e.data["gate"], e.data["decision"])
        for e in events
        if e.type is RunEventType.GATE and e.data["specialist"] == "advisor"
    ]


async def test_a_generic_suggestion_is_refused_with_the_reason_and_the_revised_one_is_saved(
    redis: Redis, engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    llm.judge(GENERIC)
    run = await _advised_run(
        engine, ctx, llm, replies=[suggest("Improve marketing"), *three(), finish_advice()]
    )

    assert "could be given to any idea" in llm.shown(2)
    assert [s["title"] for s in await _suggestions(engine, run)] == [
        "Suggestion 0",
        "Suggestion 1",
        "Suggestion 2",
    ]
    assert await _gate_events(redis, run) == [
        ("advice_output", "retried"),
        ("advice_output", "passed"),
        ("advice_output", "passed"),
        ("advice_output", "passed"),
    ]


async def test_the_judge_sees_the_suggestion_the_idea_and_the_weakest_parameters(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    await _advised_run(engine, ctx, llm)

    seen = str(llm.judge_bodies[0]["messages"])
    assert "Suggestion 0" in seen and "problem_severity" in seen
    assert "idea_text" in seen and "weakest" in seen


async def test_a_source_the_run_never_saw_is_rejected_without_a_judge_call(
    redis: Redis, engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(
        engine, ctx, llm, replies=[suggest(url=INVENTED), *three(), finish_advice()]
    )

    assert "not a source from the research" in llm.shown(2)
    assert len(llm.judge_bodies) == 3  # the three that passed the code checks, none for this
    assert (await _gate_events(redis, run))[0] == ("advice_output", "retried")
    assert len(await _suggestions(engine, run)) == 3


async def test_a_suggestion_aimed_at_no_weak_parameter_is_rejected_without_a_judge_call(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(
        engine, ctx, llm, replies=[suggest("Off target", ("timing",)), *three(), finish_advice()]
    )

    assert "weakest parameters" in llm.shown(2)
    assert len(llm.judge_bodies) == 3
    assert len(await _suggestions(engine, run)) == 3


async def test_a_near_duplicate_of_a_saved_suggestion_is_rejected(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(
        engine,
        ctx,
        llm,
        replies=[
            suggest("Niche down to agencies", ("problem_severity",)),
            suggest("niche down to Agencies", ("problem_severity",)),
            suggest("Charge per seat", ("problem_severity",)),
            suggest("Add an invoice import", ("problem_severity",)),
            finish_advice(),
        ],
    )

    assert "repeats" in llm.shown(3)
    assert [s["title"] for s in await _suggestions(engine, run)] == [
        "Niche down to agencies",
        "Charge per seat",
        "Add an invoice import",
    ]


async def test_after_two_retries_the_suggestion_is_skipped_and_the_advice_goes_on(
    redis: Redis, engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    llm.judge(GENERIC, GENERIC, GENERIC)
    weak = [suggest(f"Vague {n}") for n in range(3)]
    run = await _advised_run(engine, ctx, llm, replies=[*weak, *three(), finish_advice()])

    row = await run_row(engine, run)
    assert row.status == "awaiting_user" and row.error is None
    assert "skipped" in llm.shown(4)
    assert [title for title in [s["title"] for s in await _suggestions(engine, run)]] == [
        "Suggestion 0",
        "Suggestion 1",
        "Suggestion 2",
    ]
    assert (await _gate_events(redis, run))[:3] == [
        ("advice_output", "retried"),
        ("advice_output", "retried"),
        ("advice_output", "skipped"),
    ]


async def test_a_skip_that_leaves_a_score_below_55_short_still_reaches_the_decision(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    llm.judge("PASS", "PASS", GENERIC, GENERIC, GENERIC)
    replies = [
        *three()[:2],
        *[suggest(f"Vague {n}") for n in range(3)],
        Reply(text="Nothing else is well founded."),
    ]
    run = await _advised_run(engine, ctx, llm, replies=replies)

    row = await run_row(engine, run)
    assert row.status == "awaiting_user" and row.error is None
    assert (await _pending(engine, run))["type"] == "advice_decision"
    assert len(await _suggestions(engine, run)) == 2


async def test_a_resume_after_such_a_shortfall_makes_no_model_call(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    llm.judge("PASS", "PASS", GENERIC, GENERIC, GENERIC)
    replies = [
        *three()[:2],
        *[suggest(f"Vague {n}") for n in range(3)],
        Reply(text="Nothing else is well founded."),
    ]
    run = await _advised_run(engine, ctx, llm, replies=replies)
    calls_before = (llm.calls, len(llm.judge_bodies))

    await run_job(ctx, run, resume={"decision": "continue"})

    assert (llm.calls, len(llm.judge_bodies)) == calls_before
    assert (await run_row(engine, run)).status == "succeeded"
    assert len(await _suggestions(engine, run)) == 2


async def test_when_every_suggestion_is_skipped_a_score_below_55_still_fails_the_run(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    llm.judge(GENERIC, GENERIC, GENERIC)
    replies = [*[suggest(f"Vague {n}") for n in range(3)], Reply(text="Nothing else.")]
    run = await _advised_run(engine, ctx, llm, replies=replies)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "advice.invalid_submission"
    assert await _suggestions(engine, run) == []


async def test_an_unreadable_judge_reply_lets_the_suggestion_through(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    llm.judge("this is not a verdict")
    run = await _advised_run(engine, ctx, llm)

    assert (await run_row(engine, run)).status == "awaiting_user"
    assert len(await _suggestions(engine, run)) == 3
