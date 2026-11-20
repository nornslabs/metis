"""The Advisor through the ``run_graph`` job, from ``advising`` to the user's decision.

Seam: the job function, called as Arq would, on real Postgres as ``metis_app``, real Redis and
the real checkpointer, with a scripted OpenAI-compatible LLM and an in-process Exa MCP server
(the same seam as ``test_scorer.py``). The real Scorer runs first, so each test starts from a
stored score. The ``advice_decision`` interrupt is answered by calling the job with ``resume``,
as the resume route does. Tests check what the user and the database see: the saved suggestions,
the interrupt, the score runs, the idea's text and stage, the run status.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.tools.advice import weakest_params
from metis.core.db import set_workspace
from metis.core.events import RunEventType
from metis.modules import scoring
from metis.modules.scoring import ScoreBand, ScoreParam, ScoreRun
from tests.agent.interview_helpers import Call, Reply, ScriptedLLM
from tests.agent.run_job_helpers import (
    QueuedRun,
    events_of,
    idea_stage,
    job_ctx,
    keyed_run,
    run_job,
    run_row,
)
from tests.agent.score_helpers import (
    REPORT,
    RIVAL,
    SEARCHED,
    WEIGHTED_54,
    WEIGHTED_55,
    call,
    current_score,
    finished,
    score_runs,
    scoring_run,
    search,
    submit,
)
from tests.modules.identity.fake_exa_mcp import FakeExaMcp

# WEIGHTED_54 loses 100, 100, 75, 75, 50 and 60 points: the weakest are these three.
WEAKEST_54 = ["problem_severity", "uniqueness", "market_demand"]
OVERALL_70 = {name: 7 for name in WEIGHTED_55}


def suggest(
    title: str = "Niche down to agencies",
    params: tuple[str, ...] = ("uniqueness",),
    url: str = REPORT,
    kind: str = "niche",
) -> Reply:
    return Reply(
        calls=(
            Call(
                "save_suggestion",
                {
                    "kind": kind,
                    "title": title,
                    "rationale": f"{title} fills a gap the research shows.",
                    "target_params": list(params),
                    "expected_impact": "uniqueness up by about 2 marks",
                    "evidence": [{"url": url, "title": "Source", "quote": "A sentence."}],
                },
            ),
        )
    )


def three(url: str = REPORT) -> list[Reply]:
    return [suggest(f"Suggestion {n}", ("problem_severity",), url) for n in range(3)]


def finish_advice() -> Reply:
    return call("finish_advice")


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


async def _suggestions(engine: AsyncEngine, run: QueuedRun) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT s.id, s.kind, s.title, s.status, s.target_params, s.score_run_id "
                "FROM scoring.suggestions s JOIN scoring.score_runs r ON r.id = s.score_run_id "
                "WHERE r.run_id = :run ORDER BY s.id"
            ),
            {"run": run.run_id},
        )
        return [dict(row._mapping) for row in result.all()]


async def _idea_text(engine: AsyncEngine, run: QueuedRun) -> str:
    async with engine.connect() as conn:
        value = await conn.scalar(
            text(
                "SELECT raw_text FROM ideas.ideas "
                "WHERE id = (SELECT idea_id FROM ideas.workflow_runs WHERE id = :id)"
            ),
            {"id": run.run_id},
        )
    return str(value)


async def _advised_run(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    llm: ScriptedLLM,
    *,
    marks: dict[str, int] | None = None,
    replies: list[Reply] | None = None,
    exa_key: bool = True,
) -> QueuedRun:
    """A run scored by the real Scorer, then advised: ``replies`` are the Advisor's."""
    run = await scoring_run(engine, exa_key=exa_key)
    llm.add(
        submit(marks or WEIGHTED_54),
        *(replies if replies is not None else [*three(), finish_advice()]),
    )
    await run_job(ctx, run)
    return run


async def _score_run_ids(engine: AsyncEngine, run: QueuedRun) -> list[UUID]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT id FROM scoring.score_runs WHERE run_id = :run"), {"run": run.run_id}
        )
        return [row[0] for row in result.all()]


@asynccontextmanager
async def in_workspace_session(engine: AsyncEngine, run: QueuedRun) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(engine) as session:
        await set_workspace(session, run.workspace_id)
        yield session


async def _pending(engine: AsyncEngine, run: QueuedRun) -> dict[str, Any]:
    pending = (await run_row(engine, run)).pending_interrupt
    assert pending is not None
    return pending


async def test_a_score_below_55_gets_three_sourced_suggestions_and_a_decision_prompt(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(engine, ctx, llm)

    saved = await _suggestions(engine, run)
    pending = await _pending(engine, run)
    assert (await run_row(engine, run)).status == "awaiting_user"
    assert len(saved) == 3
    assert {s["status"] for s in saved} == {"open"}
    assert pending["type"] == "advice_decision"
    assert (pending["total"], pending["band"]) == (54, "advise")
    assert pending["suggestion_ids"] == [str(s["id"]) for s in saved]
    assert await idea_stage(engine, run) == "advising"


async def test_the_model_is_shown_the_score_the_weakest_parameters_and_how_many_to_save(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(engine, ctx, llm)

    seen = llm.shown(1)  # the Advisor's first call (the Scorer made call 0)
    assert "Weakest parameters, worst first: " + ", ".join(WEAKEST_54) in seen
    assert "Save 3 to 5 suggestions." in seen
    assert "54 of 100" in seen and REPORT in seen
    assert tool_names_of_second_loop(llm) >= {"save_suggestion", "finish_advice", "kb_lookup"}
    assert (await run_row(engine, run)).status == "awaiting_user"


def tool_names_of_second_loop(llm: ScriptedLLM) -> set[str]:
    return {tool["function"]["name"] for tool in llm.bodies[1]["tools"]}


async def test_a_promising_idea_gets_at_most_two_suggestions_and_goes_on_to_the_spec(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(
        engine,
        ctx,
        llm,
        marks=WEIGHTED_55,
        replies=[suggest("One"), suggest("Two"), suggest("Three"), finish_advice()],
    )

    assert (await run_row(engine, run)).status == "succeeded"
    assert len(await _suggestions(engine, run)) == 2
    assert "limit of 2 suggestions" in llm.shown(4)  # the third save was refused
    assert await idea_stage(engine, run) == "exported"
    assert "advisor" in finished(await events_of(redis, run))


async def test_a_promising_idea_may_get_no_suggestion(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(engine, ctx, llm, marks=WEIGHTED_55, replies=[finish_advice()])

    assert (await run_row(engine, run)).status == "succeeded"
    assert await _suggestions(engine, run) == []


async def test_a_strong_idea_is_not_advised(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    llm.add(submit({name: 8 for name in WEIGHTED_55}))

    await run_job(ctx, run)

    assert "advisor" not in finished(await events_of(redis, run))
    assert await _suggestions(engine, run) == []


async def test_evidence_the_run_never_saw_is_refused_and_known_urls_are_accepted(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(
        engine,
        ctx,
        llm,
        replies=[
            suggest(url="https://invented.example.com/page"),
            suggest("Two", url=RIVAL),
            suggest("Three", url=REPORT + "#top"),
            suggest("Four", url=REPORT),
            finish_advice(),
        ],
    )

    assert "not a source from the research" in llm.shown(2)
    assert (await run_row(engine, run)).status == "awaiting_user"
    assert [s["title"] for s in await _suggestions(engine, run)] == ["Two", "Three", "Four"]


async def test_a_suggestion_must_target_one_of_the_weakest_parameters(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(
        engine,
        ctx,
        llm,
        replies=[suggest("Off target", ("timing",)), *three(), finish_advice()],
    )

    assert "weakest parameters: " + ", ".join(WEAKEST_54) in llm.shown(2)
    assert len(await _suggestions(engine, run)) == 3


async def test_a_suggestion_needs_a_source(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    bare = suggest()
    bare.calls[0].args["evidence"] = []
    run = await _advised_run(engine, ctx, llm, replies=[bare, *three(), finish_advice()])

    assert "evidence" in llm.shown(2)
    assert len(await _suggestions(engine, run)) == 3


async def test_a_sixth_suggestion_is_refused(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    replies = [suggest(f"S{n}", ("problem_severity",)) for n in range(6)]
    run = await _advised_run(engine, ctx, llm, replies=[*replies, finish_advice()])

    assert "limit of 5 suggestions" in llm.shown(7)
    assert len(await _suggestions(engine, run)) == 5


async def test_finishing_early_is_refused_once_and_the_advice_goes_on(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(
        engine,
        ctx,
        llm,
        replies=[
            suggest("One"),
            suggest("Two"),
            finish_advice(),
            suggest("Three"),
            finish_advice(),
        ],
    )

    assert "save 1 more" in llm.shown(4)
    assert (await run_row(engine, run)).status == "awaiting_user"
    assert len(await _suggestions(engine, run)) == 3


async def test_two_early_finishes_fail_the_run_and_keep_what_was_saved(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(
        engine, ctx, llm, replies=[suggest("One"), finish_advice(), finish_advice()]
    )

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "advice.invalid_submission"
    assert len(await _suggestions(engine, run)) == 1
    assert len(await score_runs(engine, run)) == 1


async def test_a_loop_that_ends_without_enough_suggestions_fails_the_run(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(engine, ctx, llm, replies=[Reply(text="Nothing to add.")])

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "advice.invalid_submission"


async def test_the_advisors_searches_stop_at_three_and_a_found_url_is_a_source(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, exa: FakeExaMcp
) -> None:
    run = await _advised_run(
        engine,
        ctx,
        llm,
        replies=[
            *(search(f"gap {n}") for n in range(4)),
            *three(SEARCHED),
            finish_advice(),
        ],
    )

    assert len(exa.tool_calls) == 3
    assert "limit" in llm.shown(5)  # the 4th search was answered with the limit message
    assert len(await _suggestions(engine, run)) == 3


async def test_a_workspace_without_an_exa_key_is_still_advised_without_a_search_tool(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, exa: FakeExaMcp
) -> None:
    run = await _advised_run(engine, ctx, llm, exa_key=False)

    assert (await run_row(engine, run)).status == "awaiting_user"
    assert "web_search_exa" not in tool_names_of_second_loop(llm)
    assert "Web search is not available" in llm.shown(1)
    assert (exa.api_keys, exa.tool_calls) == ([], [])


async def test_continue_goes_to_the_spec_with_one_score_run_and_makes_no_model_call(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(engine, ctx, llm)
    calls_before = llm.calls

    await run_job(ctx, run, resume={"decision": "continue"})

    assert llm.calls == calls_before  # the node re-ran on resume without advising again
    assert (await run_row(engine, run)).status == "succeeded"
    assert len(await _suggestions(engine, run)) == 3
    assert len(await score_runs(engine, run)) == 1
    assert finished(await events_of(redis, run)).count("advisor") == 1
    assert await idea_stage(engine, run) != "advising"


async def test_stop_ends_the_run_with_the_idea_left_at_advising(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(engine, ctx, llm)

    await run_job(ctx, run, resume={"decision": "stop"})

    assert (await run_row(engine, run)).status == "succeeded"
    assert await idea_stage(engine, run) == "advising"
    assert len(await score_runs(engine, run)) == 1


async def test_revise_saves_the_new_text_and_scores_again_once(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(engine, ctx, llm)
    saved = await _suggestions(engine, run)
    accepted, other = saved[0], saved[1]
    llm.add(submit(OVERALL_70))

    await run_job(
        ctx,
        run,
        resume={
            "decision": "revise",
            "revised_text": "A freelancer CRM that also sends invoices.",
            "accepted_suggestion_ids": [str(accepted["id"])],
        },
    )

    assert (await run_row(engine, run)).status == "succeeded"
    text_now = await _idea_text(engine, run)
    assert text_now.startswith("A freelancer CRM that also sends invoices.")
    assert f"Accepted improvements:\n- {accepted['title']}:" in text_now
    assert other["title"] not in text_now
    statuses = {s["id"]: s["status"] for s in await _suggestions(engine, run)}
    assert statuses[accepted["id"]] == "accepted" and statuses[other["id"]] == "open"
    runs = await score_runs(engine, run)
    assert sorted(total for total, _, _ in runs) == [54, 70]
    assert await current_score(engine, run) == 70
    first, second = sorted(await _score_run_ids(engine, run))
    async with in_workspace_session(engine, run) as session:
        compared = await scoring.diff(session, run.workspace_id, first, second)
    assert compared.total_delta == 16
    assert finished(await events_of(redis, run)).count("advisor") == 1  # one Advisor pass per run
    assert len([e for e in await events_of(redis, run) if e.type is RunEventType.SCORE]) == 2
    assert await idea_stage(engine, run) != "advising"


async def test_the_rescore_has_its_own_search_budget(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, exa: FakeExaMcp
) -> None:
    run = await _advised_run(engine, ctx, llm)
    for n in range(3):
        llm.add(search(f"recheck {n}"))
    llm.add(submit(OVERALL_70, url=SEARCHED))

    await run_job(
        ctx, run, resume={"decision": "revise", "revised_text": "A freelancer CRM with invoices."}
    )

    assert len(exa.tool_calls) == 3
    assert len(await score_runs(engine, run)) == 2


async def test_revise_drops_the_notes_that_do_not_fit_and_says_so(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(engine, ctx, llm)
    saved = await _suggestions(engine, run)
    llm.add(submit(OVERALL_70))

    await run_job(
        ctx,
        run,
        resume={
            "decision": "revise",
            "revised_text": "x" * 9_990,
            "accepted_suggestion_ids": [str(saved[0]["id"])],
        },
    )

    assert await _idea_text(engine, run) == "x" * 9_990
    notices = [e.data["code"] for e in await events_of(redis, run) if e.type is RunEventType.NOTICE]
    assert "advice.notes_dropped" in notices


async def test_accepted_ids_that_are_not_this_ideas_suggestions_are_ignored(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(engine, ctx, llm)
    llm.add(submit(OVERALL_70))
    stranger = UUID(int=1)

    await run_job(
        ctx,
        run,
        resume={
            "decision": "revise",
            "revised_text": "A freelancer CRM with invoices.",
            "accepted_suggestion_ids": [str(stranger)],
        },
    )

    assert "Accepted improvements" not in await _idea_text(engine, run)
    assert {s["status"] for s in await _suggestions(engine, run)} == {"open"}


async def test_a_run_that_reaches_the_advisor_without_a_score_goes_on_to_the_spec(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await keyed_run(engine, stage="advising")

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "succeeded"
    assert llm.calls == 0
    assert await current_score(engine, run) is None


async def test_a_loop_that_never_settles_fails_with_the_step_limit(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(engine, ctx, llm, replies=[search(f"gap {n}") for n in range(50)])

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "run.step_limit_reached"


async def test_a_promising_idea_whose_advice_never_settles_still_goes_on(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(
        engine, ctx, llm, marks=WEIGHTED_55, replies=[search(f"gap {n}") for n in range(50)]
    )

    assert (await run_row(engine, run)).status == "succeeded"


async def test_a_rerun_with_the_suggestions_saved_asks_again_without_a_model_call(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _advised_run(engine, ctx, llm)
    calls_before = llm.calls
    # The worker died after the suggestions were saved but before the checkpoint.
    async with engine.begin() as conn:
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            await conn.execute(
                text(f"DELETE FROM agent.{table} WHERE thread_id = :id"), {"id": str(run.run_id)}
            )
        await conn.execute(
            text("UPDATE ideas.workflow_runs SET status = 'running' WHERE id = :id"),
            {"id": run.run_id},
        )

    await run_job(ctx, run)

    assert llm.calls == calls_before
    assert (await run_row(engine, run)).status == "awaiting_user"
    assert len(await _suggestions(engine, run)) == 3
    assert (await _pending(engine, run))["type"] == "advice_decision"


def _result(param: ScoreParam, weight: int, raw: int) -> dict[str, Any]:
    return {
        "param": param,
        "weight": weight,
        "raw": raw,
        "weighted": weight * raw / 10,
        "reason": "Because.",
        "confidence": 0.5,
        "no_evidence": True,
        "evidence": [],
    }


def _score(raws: dict[ScoreParam, int]) -> ScoreRun:
    weights = {
        ScoreParam.PROBLEM_SEVERITY: 25,
        ScoreParam.UNIQUENESS: 25,
        ScoreParam.MARKET_DEMAND: 15,
        ScoreParam.VALUE: 15,
        ScoreParam.FEASIBILITY: 10,
        ScoreParam.TIMING: 10,
    }
    return ScoreRun.model_validate(
        {
            "id": UUID(int=2),
            "idea_id": UUID(int=3),
            "run_id": UUID(int=4),
            "rubric_version": 1,
            "trigger": "manual",
            "total": 50,
            "band": ScoreBand.ADVISE,
            "created_at": "2026-11-20T10:00:00Z",
            "weights": weights,
            "params": [_result(p, weights[p], raws[p]) for p in ScoreParam],
        }
    )


def test_the_weakest_parameters_are_those_that_lost_the_most_points() -> None:
    score = _score(
        {
            ScoreParam.PROBLEM_SEVERITY: 9,  # loses 25
            ScoreParam.UNIQUENESS: 4,  # loses 150
            ScoreParam.MARKET_DEMAND: 0,  # loses 150
            ScoreParam.VALUE: 5,
            ScoreParam.FEASIBILITY: 1,
            ScoreParam.TIMING: 8,
        }
    )

    # A tie (150 each) goes to the heavier weight.
    assert weakest_params(score, 3) == (
        ScoreParam.UNIQUENESS,
        ScoreParam.MARKET_DEMAND,
        ScoreParam.FEASIBILITY,
    )
