"""The Architect through the ``run_graph`` job, from ``spec_draft`` to the user's confirmation.

Seam: the job function, called as Arq would, on real Postgres as ``metis_app``, real Redis and
the real checkpointer, with a scripted OpenAI-compatible LLM (the same seam as
``test_advisor.py``). The ``spec_review`` interrupt is answered the way the confirm route does:
the version is confirmed through the ``ideas`` service, then the job is called with ``resume``.
Tests check what the user and the database see: the saved versions, the idea's kind and stage,
the interrupt, the run status.
"""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.helpers.ids import uuid7
from metis.modules import ideas
from metis.modules.ideas import NewSpecVersion, SpecSource
from tests.agent.interview_helpers import Reply, ScriptedLLM
from tests.agent.run_job_helpers import (
    QueuedRun,
    events_of,
    idea_stage,
    job_ctx,
    keyed_run,
    run_job,
    run_row,
)
from tests.agent.score_helpers import REPORT, call, finished, save_snapshot
from tests.modules.scoring.scoring_helpers import in_workspace

SECTIONS = {
    "problem": "Freelancers lose track of leads.",
    "target_users": "Solo freelancers.",
    "solution": "A tiny CRM.",
    "key_features": "- MVP: a lead list\n- Later: reminders",
    "non_goals": "Team features.",
    "competitive_edge": "Simple and cheap.",
    "success_metrics": "50 weekly active users.",
    "risks": "Crowded market.",
    "open_questions": "None.",
}

SCORE_PARAMS = (
    "problem_severity",
    "uniqueness",
    "market_demand",
    "value",
    "feasibility",
    "timing",
)


def save_spec(kind: str = "software", **overrides: str) -> Reply:
    return call("save_spec", kind=kind, **{**SECTIONS, **overrides})


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
    return job_ctx(redis, app_sessions, llm=llm, architect=True)


async def _spec_run(engine: AsyncEngine, *, snapshot: bool = True) -> QueuedRun:
    run = await keyed_run(engine, stage="spec_draft")
    if snapshot:
        await save_snapshot(engine, run)
    return run


async def _versions(engine: AsyncEngine, run: QueuedRun) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT v.number, v.source, v.content_md, v.run_id, v.sections "
                "FROM ideas.spec_versions v JOIN ideas.workflow_runs r ON r.idea_id = v.idea_id "
                "WHERE r.id = :run ORDER BY v.number"
            ),
            {"run": run.run_id},
        )
        return [dict(row._mapping) for row in result.all()]


async def _kind(engine: AsyncEngine, run: QueuedRun) -> str | None:
    async with engine.connect() as conn:
        value = await conn.scalar(
            text(
                "SELECT kind FROM ideas.ideas "
                "WHERE id = (SELECT idea_id FROM ideas.workflow_runs WHERE id = :id)"
            ),
            {"id": run.run_id},
        )
    return None if value is None else str(value)


async def _idea_id(engine: AsyncEngine, run: QueuedRun) -> Any:
    async with engine.connect() as conn:
        return await conn.scalar(
            text("SELECT idea_id FROM ideas.workflow_runs WHERE id = :id"), {"id": run.run_id}
        )


async def _pending(engine: AsyncEngine, run: QueuedRun) -> dict[str, Any]:
    pending = (await run_row(engine, run)).pending_interrupt
    assert pending is not None
    return pending


async def _confirm(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession], run: QueuedRun, number: int
) -> None:
    idea_id = await _idea_id(engine, run)
    async with in_workspace(app_sessions, run.workspace_id) as session:
        await ideas.confirm_spec(session, run.workspace_id, idea_id, number)


async def _accepted_and_open_suggestions(engine: AsyncEngine, run: QueuedRun) -> None:
    """A score run with two suggestions of the run's idea: one accepted, one still open."""
    score_run_id = uuid7()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO scoring.score_runs "
                "(id, workspace_id, idea_id, run_id, rubric_version_id, trigger, total, band) "
                "SELECT :id, workspace_id, idea_id, id, 1, 'manual', 40, 'advise' "
                "FROM ideas.workflow_runs WHERE id = :run"
            ),
            {"id": score_run_id, "run": run.run_id},
        )
        await conn.execute(
            text(
                "INSERT INTO scoring.score_params (score_run_id, workspace_id, param, raw, "
                "weighted, reason, confidence, no_evidence, evidence) "
                "SELECT :id, workspace_id, p, 4, 10, 'Weak.', 0.30, true, '[]'::jsonb "
                "FROM ideas.workflow_runs, unnest(CAST(:params AS text[])) AS p WHERE id = :run"
            ),
            {"id": score_run_id, "run": run.run_id, "params": list(SCORE_PARAMS)},
        )
        for title, status in (("Niche down to agencies", "accepted"), ("Add a mobile app", "open")):
            await conn.execute(
                text(
                    "INSERT INTO scoring.suggestions (id, workspace_id, idea_id, score_run_id, "
                    "kind, title, rationale, target_params, expected_impact, evidence, status) "
                    "SELECT :id, workspace_id, idea_id, :sr, 'niche', :title, 'Because.', "
                    "ARRAY['uniqueness'], 'More', "
                    '\'[{"url": "https://example.com", "title": "T", "quote": ""}]\''
                    "::jsonb, :status FROM ideas.workflow_runs WHERE id = :run"
                ),
                {
                    "id": uuid7(),
                    "sr": score_run_id,
                    "title": title,
                    "status": status,
                    "run": run.run_id,
                },
            )


async def test_the_architect_drafts_version_one_and_waits_for_the_review(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _spec_run(engine)
    llm.add(save_spec())

    await run_job(ctx, run)

    versions = await _versions(engine, run)
    assert [(v["number"], v["source"], v["run_id"]) for v in versions] == [(1, "agent", run.run_id)]
    assert "## Key features (MVP and later)" in versions[0]["content_md"]
    assert versions[0]["sections"]["problem"] == SECTIONS["problem"]
    pending = await _pending(engine, run)
    assert (pending["type"], pending["number"], pending["kind"]) == ("spec_review", 1, "software")
    assert (await run_row(engine, run)).status == "awaiting_user"
    assert await idea_stage(engine, run) == "spec_draft"
    assert await _kind(engine, run) == "software"


async def test_the_model_is_shown_the_idea_the_research_and_only_the_accepted_advice(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _spec_run(engine)
    await _accepted_and_open_suggestions(engine, run)
    llm.add(save_spec())

    await run_job(ctx, run)

    seen = llm.shown(0)
    assert "A tiny CRM for freelancers." in seen and REPORT in seen
    assert "Niche down to agencies" in seen
    assert "Add a mobile app" not in seen
    assert {t["function"]["name"] for t in llm.bodies[0]["tools"]} == {"save_spec"}


async def test_a_kind_the_user_already_chose_is_kept(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _spec_run(engine)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE ideas.ideas SET kind = 'other' WHERE id = :id"),
            {"id": await _idea_id(engine, run)},
        )
    llm.add(save_spec("software"))

    await run_job(ctx, run)

    assert await _kind(engine, run) == "other"
    assert (await _pending(engine, run))["kind"] == "other"


async def test_a_refused_spec_is_corrected_and_stored_once(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _spec_run(engine)
    llm.add(save_spec(risks="  "), save_spec())

    await run_job(ctx, run)

    assert "empty: risks" in llm.shown(1)
    assert len(await _versions(engine, run)) == 1
    assert (await run_row(engine, run)).status == "awaiting_user"


@pytest.mark.parametrize("bad", [{"kind": "gadget"}, {"problem": "x" * 50_001}])
async def test_a_bad_kind_or_an_oversized_spec_is_refused(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, bad: dict[str, str]
) -> None:
    run = await _spec_run(engine)
    first = save_spec(**bad) if "problem" in bad else save_spec(bad["kind"])
    llm.add(first, save_spec())

    await run_job(ctx, run)

    assert "Nothing was saved" in llm.shown(1)
    assert len(await _versions(engine, run)) == 1


async def test_two_refused_specs_fail_the_run_and_store_nothing(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _spec_run(engine)
    llm.add(save_spec(risks=""), save_spec(solution=""))

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "spec.invalid_submission"
    assert await _versions(engine, run) == []


async def test_a_loop_that_ends_without_a_spec_fails_the_run(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _spec_run(engine)
    llm.add(Reply(text="Here is my spec in words."))

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "spec.invalid_submission"


async def test_confirming_resumes_the_run_to_the_end_without_another_model_call(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    llm: ScriptedLLM,
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run = await _spec_run(engine)
    llm.add(save_spec())
    await run_job(ctx, run)
    await _confirm(engine, app_sessions, run, 1)

    await run_job(ctx, run, resume={"confirmed_number": 1})

    assert (await run_row(engine, run)).status == "succeeded"
    assert llm.calls == 1
    assert len(await _versions(engine, run)) == 1
    assert await idea_stage(engine, run) == "exported"
    assert "architect" in finished(await events_of(redis, run))


async def test_the_review_shows_the_latest_version_when_the_user_already_edited_the_draft(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    llm: ScriptedLLM,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run = await _spec_run(engine)
    idea_id = await _idea_id(engine, run)
    async with in_workspace(app_sessions, run.workspace_id) as session:
        for source, base in ((SpecSource.AGENT, None), (SpecSource.USER, 1)):
            await ideas.save_spec_version(
                session,
                run.workspace_id,
                idea_id,
                NewSpecVersion(content_md="## Problem\n\nA draft.", source=source),
                base_number=base,
            )

    await run_job(ctx, run)

    assert llm.calls == 0
    assert (await _pending(engine, run))["number"] == 2


async def test_an_idea_that_already_has_a_spec_goes_straight_to_the_review(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    llm: ScriptedLLM,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run = await _spec_run(engine)
    idea_id = await _idea_id(engine, run)
    async with in_workspace(app_sessions, run.workspace_id) as session:
        await ideas.save_spec_version(
            session,
            run.workspace_id,
            idea_id,
            NewSpecVersion(content_md="## Problem\n\nEarlier draft.", source=SpecSource.AGENT),
        )

    await run_job(ctx, run)

    assert llm.calls == 0
    assert (await _pending(engine, run))["number"] == 1
    assert (await run_row(engine, run)).status == "awaiting_user"
    assert len(await _versions(engine, run)) == 1
