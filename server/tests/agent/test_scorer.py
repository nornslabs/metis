"""The Scorer through the ``run_graph`` job, from ``scoring`` to the next stage.

Seam: the job function, called as Arq would, on real Postgres as ``metis_app``, real Redis and
the real checkpointer, with a scripted OpenAI-compatible LLM and an in-process Exa MCP server
(the same seam as ``test_researcher.py``). Tests check what the user and the database see: the
stored score run, ``ideas.current_score``, the ``score`` event, the stage path, the run status.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.tools.exa import ExaCallBudget
from metis.agent.tools.score_scale import SCALE
from metis.agent.tools.scoring import SourceBook, normalize_url
from metis.core.events import RunEventType
from metis.helpers.ids import uuid7
from metis.modules.scoring import ScoreParam
from tests.agent.interview_helpers import Call, Reply, ScriptedLLM
from tests.agent.run_job_helpers import (
    events_of,
    idea_stage,
    job_ctx,
    run_job,
    run_row,
)
from tests.agent.score_helpers import (
    ADVISED_PATH,
    REPORT,
    RIVAL,
    SEARCHED,
    SPEC_PATH,
    WEIGHTED_54,
    WEIGHTED_55,
    call,
    current_score,
    finished,
    score_params,
    score_runs,
    scoring_run,
    search,
    submit,
    tool_names,
)
from tests.modules.identity.fake_exa_mcp import FakeExaMcp
from tests.modules.scoring.scoring_helpers import outbox_events


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

    return job_ctx(redis, app_sessions, llm=llm, exa=make_client, score=True)


async def test_scores_are_stored_with_evidence_and_the_total_is_computed(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    llm.add(call("get_rubric"), submit())

    await run_job(ctx, run)

    events = await events_of(redis, run)
    score_events = [e.data for e in events if e.type is RunEventType.SCORE]
    assert (await run_row(engine, run)).status == "succeeded"
    assert await score_runs(engine, run) == [(70, "promising", "manual")]
    assert await score_params(engine, run) == [
        (name, 7, False, 1)
        for name in (
            "feasibility",
            "market_demand",
            "problem_severity",
            "timing",
            "uniqueness",
            "value",
        )
    ]
    assert await current_score(engine, run) == 70
    assert [(e["total"], e["band"]) for e in score_events] == [(70, "promising")]
    assert set(score_events[0]) == {"score_run_id", "total", "band"}
    assert [p["total"] for p in await outbox_events(engine, run.workspace_id)] == [70]
    assert tool_names(llm) == {"web_search_exa", "kb_lookup", "get_rubric", "submit_scores"}
    assert "Many strong incumbents" in llm.shown(1)  # the written scale reached the model


async def test_the_seed_shows_the_model_the_research_it_scores_from(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    llm.add(submit())

    await run_job(ctx, run)

    assert "Acme is the main rival." in llm.shown(0)
    assert REPORT in llm.shown(0)
    assert RIVAL in llm.shown(0) and "$10 a month" in llm.shown(0)


@pytest.mark.parametrize(
    ("marks", "path", "total", "band"),
    [
        (WEIGHTED_54, ADVISED_PATH, 54, "advise"),
        (WEIGHTED_55, ADVISED_PATH, 55, "promising"),
        ({name: 8 for name in WEIGHTED_55}, SPEC_PATH, 80, "build"),
    ],
)
async def test_a_score_below_75_goes_to_advising_and_75_goes_to_the_spec(
    engine: AsyncEngine,
    redis: Redis,
    ctx: dict[str, Any],
    llm: ScriptedLLM,
    marks: dict[str, int],
    path: list[str],
    total: int,
    band: str,
) -> None:
    run = await scoring_run(engine)
    llm.add(submit(marks))

    await run_job(ctx, run)

    assert finished(await events_of(redis, run)) == path
    # One score run per workflow run: the pass after the (stub) Advisor only routes.
    assert [(t, b) for t, b, _ in await score_runs(engine, run)] == [(total, band)]
    assert llm.calls == 1


async def test_a_missing_parameter_is_refused_once_and_the_corrected_score_is_stored(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    five = {name: 7 for name in list(WEIGHTED_55)[:5]}
    llm.add(submit(five), submit())

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "succeeded"
    assert "missing parameters" in llm.shown(1)
    assert len(await score_runs(engine, run)) == 1


async def test_evidence_the_run_never_saw_is_refused_and_a_known_url_is_accepted(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    llm.add(submit(url="https://invented.example.com/page"), submit(url=REPORT + "/#top"))

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "succeeded"
    assert "not a source from the research" in llm.shown(1)
    assert len(await score_runs(engine, run)) == 1


async def test_two_refused_submissions_fail_the_run_and_store_no_score(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    llm.add(
        submit(url="https://invented.example.com/a"), submit(url="https://invented.example.com/b")
    )

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "score.invalid_submission"
    assert await score_runs(engine, run) == []
    assert await current_score(engine, run) is None
    assert [e for e in await events_of(redis, run) if e.type is RunEventType.SCORE] == []


async def test_a_loop_that_ends_without_submitting_fails_the_run(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    llm.add(Reply(text="I think the idea is fine."))

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "score.invalid_submission"


async def test_a_url_from_the_scorers_own_search_is_accepted_and_searches_stop_at_three(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, exa: FakeExaMcp
) -> None:
    run = await scoring_run(engine)
    for n in range(4):
        llm.add(search(f"market check {n}"))
    llm.add(submit(url=SEARCHED))

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "succeeded"
    assert len(exa.tool_calls) == 3
    assert "limit" in llm.shown(4)  # the 4th search was answered with the limit message
    assert len(await score_runs(engine, run)) == 1


async def test_the_scorers_search_budget_is_separate_from_the_researchers(redis: Redis) -> None:
    run_id = uuid7()
    researcher = ExaCallBudget(redis, run_id, 12)
    scorer = ExaCallBudget(redis, run_id, 3, "score_searches")

    taken = [await researcher.take() for _ in range(12)] + [await scorer.take() for _ in range(4)]

    assert taken == [True] * 12 + [True, True, True, False]


async def test_a_score_with_no_research_and_no_sources_is_accepted_as_no_evidence(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine, snapshot=False)
    llm.add(submit(url=None))

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "succeeded"
    assert "none was done" in llm.shown(0)
    assert {no_evidence for _, _, no_evidence, _ in await score_params(engine, run)} == {True}


async def test_no_evidence_with_a_high_confidence_is_refused(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine, snapshot=False)
    bad = submit(url=None)
    bad.calls[0].args["params"][0]["confidence"] = 0.9
    llm.add(bad, submit(url=None))

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "succeeded"
    assert "confidence" in llm.shown(1)


async def test_a_workspace_without_an_exa_key_is_still_scored_without_a_search_tool(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, exa: FakeExaMcp
) -> None:
    run = await scoring_run(engine, exa_key=False)
    llm.add(submit())

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "succeeded"
    assert len(await score_runs(engine, run)) == 1
    assert tool_names(llm) == {"kb_lookup", "get_rubric", "submit_scores"}
    assert "Web search is not available" in llm.shown(0)
    assert (exa.api_keys, exa.tool_calls) == ([], [])


async def test_a_rerun_after_the_score_was_stored_makes_no_model_call(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    llm.add(submit())
    await run_job(ctx, run)
    calls_before = llm.calls
    # The worker died after the score was stored but before the checkpoint.
    async with engine.begin() as conn:
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            await conn.execute(
                text(f"DELETE FROM agent.{table} WHERE thread_id = :id"), {"id": str(run.run_id)}
            )
        await conn.execute(
            text("UPDATE ideas.workflow_runs SET status = 'running' WHERE id = :id"),
            {"id": run.run_id},
        )
        await conn.execute(
            text(
                "UPDATE ideas.ideas SET stage = 'scoring' "
                "WHERE id = (SELECT idea_id FROM ideas.workflow_runs WHERE id = :id)"
            ),
            {"id": run.run_id},
        )

    await run_job(ctx, run)

    assert llm.calls == calls_before
    assert len(await score_runs(engine, run)) == 1
    assert (await run_row(engine, run)).status == "succeeded"


async def test_a_loop_that_never_settles_fails_with_the_step_limit(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    for _ in range(40):
        llm.add(call("get_rubric"))

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "run.step_limit_reached"
    assert await score_runs(engine, run) == []


async def test_the_stage_stays_scoring_for_a_failed_run(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    llm.add(Reply(text="no score"))

    await run_job(ctx, run)

    assert await idea_stage(engine, run) == "scoring"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" https://a.example.com/x/ ", "https://a.example.com/x"),
        ("https://a.example.com/x#section", "https://a.example.com/x"),
        ("https://a.example.com", "https://a.example.com"),
    ],
)
def test_urls_are_compared_without_a_fragment_or_a_trailing_slash(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


def test_a_source_book_knows_only_the_urls_it_was_given() -> None:
    book = SourceBook()
    book.add(["https://a.example.com/x/"])

    assert book.knows("https://a.example.com/x#top")
    assert not book.knows("https://b.example.com/x")


async def test_an_evidence_url_from_a_snapshot_competitor_is_accepted(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    llm.add(submit(url=RIVAL))

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "succeeded"
    assert llm.calls == 1


async def test_a_total_or_band_stated_by_the_model_is_ignored(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    claim = submit()
    claim.calls[0].args.update({"total": 100, "band": "build"})
    llm.add(claim)

    await run_job(ctx, run)

    assert await score_runs(engine, run) == [(70, "promising", "manual")]


async def test_malformed_entries_count_as_refusals_and_two_of_them_fail_the_run(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    bad = Reply(calls=(Call("submit_scores", {"params": [{"param": "value", "raw": "seven"}]}),))
    llm.add(bad, bad)

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "score.invalid_submission"
    assert "raw" in llm.shown(1)  # the model was told which field is wrong


async def test_a_key_that_failed_its_test_is_scored_without_the_search_tool(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE identity.provider_keys SET last_test_ok = false "
                "WHERE workspace_id = :ws AND kind = 'exa'"
            ),
            {"ws": run.workspace_id},
        )
    llm.add(submit())

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "succeeded"
    assert "web_search_exa" not in tool_names(llm)


def test_the_written_scale_covers_every_parameter_with_four_anchors() -> None:
    assert set(SCALE) == set(ScoreParam)
    assert all(set(anchors) == {2, 5, 8, 10} for anchors in SCALE.values())


async def test_stringified_json_params_are_accepted(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    import json

    run = await scoring_run(engine)
    raw_params = submit().calls[0].args["params"]
    llm.add(Reply(calls=(Call("submit_scores", {"params": json.dumps(raw_params)}),)))

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "succeeded"
    assert await score_runs(engine, run) == [(70, "promising", "manual")]


async def test_invalid_json_string_params_count_as_refusals(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await scoring_run(engine)
    raw = '[{"param": "value", "reason": unquoted}]'
    bad = Reply(calls=(Call("submit_scores", {"params": raw}),))
    llm.add(bad, bad)

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "score.invalid_submission"
    assert "invalid JSON" in llm.shown(1)


def test_parse_accepts_json_string_and_rejects_invalid_json_string() -> None:
    import json

    from metis.agent.tools.scoring import _parse

    raw_params = submit().calls[0].args["params"]
    entries, problems = _parse(json.dumps(raw_params))
    assert problems == []
    assert len(entries) == 6

    entries, problems = _parse('[{"param": "value", "reason": unquoted}]')
    assert entries == ()
    assert len(problems) == 1
    assert "invalid JSON string" in problems[0]

    entries, problems = _parse('{"not": "a list"}')
    assert entries == ()
    assert problems == ["params: must be a JSON array"]
