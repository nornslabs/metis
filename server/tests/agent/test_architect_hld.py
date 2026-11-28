"""The Architect's HLD (SHIP-460) through the ``run_graph`` job.

Seam: the job function, as in ``test_architect.py`` (real Postgres as ``metis_app``, real Redis
and checkpointer, a scripted OpenAI-compatible LLM). The ``spec_review`` and ``question``
interrupts are answered the way the routes do: the version is confirmed through the ``ideas``
service, then the job is called with ``resume``. Tests check what the user and the database see:
the saved HLDs, the interview, the interrupt, the spec overview and the run status.
"""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.tools.hld import BUILD_LANGUAGE_QUESTION, SaveHldArgs, render_hld_markdown
from metis.modules import ideas
from metis.modules.ideas import NewSpecVersion, SpecSource
from tests.agent.interview_helpers import ScriptedLLM
from tests.agent.run_job_helpers import QueuedRun, job_ctx, run_job, run_row
from tests.agent.score_helpers import call
from tests.agent.test_architect import (
    HLD_FIELDS,
    _confirm,
    _idea_id,
    _pending,
    _spec_run,
    save_hld,
    save_spec,
)
from tests.modules.scoring.scoring_helpers import in_workspace

OPTIONS = [
    {"label": "Python", "recommended": True},
    {"label": "TypeScript"},
    {"label": "Go"},
]


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


async def _hlds(engine: AsyncEngine, run: QueuedRun) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT h.spec_version_number, h.build_language, h.content_md "
                "FROM ideas.spec_hlds h JOIN ideas.workflow_runs r ON r.idea_id = h.idea_id "
                "WHERE r.id = :run ORDER BY h.spec_version_number"
            ),
            {"run": run.run_id},
        )
        return [dict(row._mapping) for row in result.all()]


async def _noted_answers(engine: AsyncEngine, run: QueuedRun) -> list[str]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT answer FROM ideas.interview_turns WHERE run_id = :run AND question = :q"),
            {"run": run.run_id, "q": BUILD_LANGUAGE_QUESTION},
        )
        return [str(row[0]) for row in result.all()]


async def _overview(
    app_sessions: async_sessionmaker[AsyncSession], run: QueuedRun, idea_id: Any
) -> ideas.SpecOverview:
    async with in_workspace(app_sessions, run.workspace_id) as session:
        return await ideas.get_spec_overview(session, run.workspace_id, idea_id)


def _tools(llm: ScriptedLLM, call_index: int) -> set[str]:
    return {t["function"]["name"] for t in llm.bodies[call_index]["tools"]}


async def test_a_software_idea_gets_a_blueprint_hld_with_spec_v1_before_the_review(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    llm: ScriptedLLM,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run = await _spec_run(engine)
    llm.add(save_spec(), save_hld())

    await run_job(ctx, run)

    [hld] = await _hlds(engine, run)
    assert (hld["spec_version_number"], hld["build_language"]) == (1, "Python")
    assert "## MVP components" in hld["content_md"] and "### Leads API" in hld["content_md"]
    assert "```" not in hld["content_md"]
    assert (await _pending(engine, run))["type"] == "spec_review"
    overview = await _overview(app_sessions, run, await _idea_id(engine, run))
    assert overview.hld is not None and overview.hld.stale is False


async def test_the_hld_model_is_shown_the_spec_and_may_ask_for_the_language(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _spec_run(engine)
    llm.add(save_spec(), save_hld())

    await run_job(ctx, run)

    assert "Freelancers lose track of leads." in llm.shown(1)
    assert "Build language: not decided yet" in llm.shown(1)
    assert _tools(llm, 1) == {"save_hld", "ask_build_language"}


async def test_a_language_the_idea_names_is_not_asked(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _spec_run(engine)
    llm.add(save_spec(), save_hld(build_language="Rust"))

    await run_job(ctx, run)

    assert (await _pending(engine, run))["type"] == "spec_review"
    assert [h["build_language"] for h in await _hlds(engine, run)] == ["Rust"]
    assert await _noted_answers(engine, run) == []


async def test_an_unnamed_language_is_asked_once_and_the_answer_is_kept(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _spec_run(engine)
    llm.add(
        save_spec(),
        call("ask_build_language", options=OPTIONS),
        save_hld(build_language="TypeScript"),
    )

    await run_job(ctx, run)

    question = await _pending(engine, run)
    assert question["type"] == "question" and question["question"] == BUILD_LANGUAGE_QUESTION
    assert [o["label"] for o in question["options"]] == ["Python", "TypeScript", "Go"]
    assert "index" not in question and "total" not in question
    assert await _hlds(engine, run) == []

    await run_job(ctx, run, resume="TypeScript")

    assert "TypeScript" in llm.shown(2)
    assert [h["build_language"] for h in await _hlds(engine, run)] == ["TypeScript"]
    assert await _noted_answers(engine, run) == ["TypeScript"]
    assert (await _pending(engine, run))["type"] == "spec_review"
    assert llm.calls == 3  # the spec, the question, the HLD: nothing is asked twice


async def test_another_kind_of_idea_gets_no_hld(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    llm: ScriptedLLM,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run = await _spec_run(engine)
    llm.add(save_spec("other"))

    await run_job(ctx, run)

    assert llm.calls == 1
    assert await _hlds(engine, run) == []
    overview = await _overview(app_sessions, run, await _idea_id(engine, run))
    assert overview.hld is None
    assert (await _pending(engine, run))["type"] == "spec_review"


async def test_a_refused_hld_is_fixed_and_saved_once(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _spec_run(engine)
    coded = save_hld(overview="Use this:\n```python\nprint(1)\n```")
    llm.add(save_spec(), coded, save_hld())

    await run_job(ctx, run)

    assert "remove code blocks" in llm.shown(2)
    assert len(await _hlds(engine, run)) == 1


async def test_two_refused_hlds_leave_the_spec_review_without_one(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    llm: ScriptedLLM,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run = await _spec_run(engine)
    llm.add(save_spec(), save_hld(overview=""), save_hld(components=[]))

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "awaiting_user"
    assert (await _pending(engine, run))["type"] == "spec_review"
    assert await _hlds(engine, run) == []
    overview = await _overview(app_sessions, run, await _idea_id(engine, run))
    assert overview.latest is not None and overview.hld is None


async def test_an_edited_spec_marks_the_hld_stale_and_confirming_writes_a_fresh_one(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    llm: ScriptedLLM,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run = await _spec_run(engine)
    idea_id = await _idea_id(engine, run)
    llm.add(save_spec(), save_hld())
    await run_job(ctx, run)
    async with in_workspace(app_sessions, run.workspace_id) as session:
        await ideas.save_spec_version(
            session,
            run.workspace_id,
            idea_id,
            NewSpecVersion(content_md="## Problem\n\nA new angle.", source=SpecSource.USER),
            base_number=1,
        )
    stale = (await _overview(app_sessions, run, idea_id)).hld
    assert stale is not None and stale.stale is True
    await _confirm(engine, app_sessions, run, 2)
    llm.add(save_hld(build_language="Ignored by the saved language"))

    await run_job(ctx, run, resume={"confirmed_number": 2})

    assert [h["spec_version_number"] for h in await _hlds(engine, run)] == [1, 2]
    assert _tools(llm, 2) == {"save_hld"}  # the language is known: no question
    assert "Build language: Python, from the earlier HLD. Keep it unless the spec" in llm.shown(2)
    fresh = (await _overview(app_sessions, run, idea_id)).hld
    assert fresh is not None and fresh.stale is False and fresh.spec_version_number == 2
    assert (await run_row(engine, run)).status == "succeeded"


async def test_confirming_does_not_ask_for_a_language_when_the_first_hld_was_never_written(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    llm: ScriptedLLM,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run = await _spec_run(engine)
    llm.add(save_spec(), save_hld(overview=""), save_hld(components=[]))
    await run_job(ctx, run)
    await _confirm(engine, app_sessions, run, 1)

    await run_job(ctx, run, resume={"confirmed_number": 1})

    assert llm.calls == 3  # no third HLD attempt, and so no question, after the review
    assert await _hlds(engine, run) == []
    assert (await run_row(engine, run)).status == "succeeded"


async def test_a_reverted_edit_is_not_stale_and_confirming_it_writes_nothing(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    llm: ScriptedLLM,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run = await _spec_run(engine)
    idea_id = await _idea_id(engine, run)
    llm.add(save_spec(), save_hld())
    await run_job(ctx, run)
    async with in_workspace(app_sessions, run.workspace_id) as session:
        first = await ideas.get_spec(session, run.workspace_id, idea_id, 1)
        await ideas.save_spec_version(
            session,
            run.workspace_id,
            idea_id,
            NewSpecVersion(content_md=first.content_md, source=SpecSource.USER),
            base_number=1,
        )
    assert (await _overview(app_sessions, run, idea_id)).hld is not None
    await _confirm(engine, app_sessions, run, 2)

    await run_job(ctx, run, resume={"confirmed_number": 2})

    assert llm.calls == 2
    assert [h["spec_version_number"] for h in await _hlds(engine, run)] == [1]


def test_the_hld_markdown_has_the_blueprint_sections_in_order() -> None:
    markdown = render_hld_markdown(SaveHldArgs.model_validate(HLD_FIELDS))

    headings = [line for line in markdown.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Overview",
        "## Build language and stack",
        "## MVP components",
        "## How the components connect",
        "## Functional requirements",
    ]
    assert "**Language:** Python" in markdown
