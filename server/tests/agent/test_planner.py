"""The Planner through the ``run_graph`` job, from ``spec_confirmed`` to a saved draft plan.

Seam: the job function, called as Arq would, on real Postgres as ``metis_app``, real Redis and
the real checkpointer, with a scripted OpenAI-compatible LLM (the same seam as
``test_architect.py``). The ``phase_review`` interrupt is answered the way the resume route
does: the job is called with ``resume``. Tests check what the user and the database see: the
interrupt, the stored plan, the run status and the stage.
"""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.prompts import load_prompt
from metis.core.events import RunEventType
from tests.agent.interview_helpers import Reply, ScriptedLLM
from tests.agent.linear_helpers import connect_workspace, mcp_client, oauth_client
from tests.agent.planner_helpers import (
    PHASES,
    TASKS,
    planning_run,
    propose,
    save_existing_plan,
    save_plan,
    stored_dep_count,
    stored_phases,
    stored_plans,
    stored_tasks,
    task,
)
from tests.agent.run_job_helpers import QueuedRun, events_of, idea_stage, job_ctx, run_job, run_row
from tests.agent.score_helpers import finished
from tests.helpers.fake_linear import FakeLinear


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
    return job_ctx(redis, app_sessions, llm=llm, planner=True)


async def _pending(engine: AsyncEngine, run: QueuedRun) -> dict[str, Any]:
    pending = (await run_row(engine, run)).pending_interrupt
    assert pending is not None
    return pending


async def _review(
    engine: AsyncEngine, ctx: dict[str, Any], run: QueuedRun, phases: list[dict[str, str]]
) -> None:
    await run_job(ctx, run, resume={"phases": phases})


async def test_the_run_pauses_on_the_proposed_phases(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, app_sessions: Any
) -> None:
    run = await planning_run(engine, app_sessions)
    llm.add(propose())

    await run_job(ctx, run)

    pending = await _pending(engine, run)
    assert pending["type"] == "phase_review"
    assert [p["name"] for p in pending["phases"]] == [p["name"] for p in PHASES]
    assert (await run_row(engine, run)).status == "awaiting_user"
    assert await stored_plans(engine, run) == []
    assert {t["function"]["name"] for t in llm.bodies[0]["tools"]} == {
        "propose_phases",
        "save_plan",
    }


async def test_approving_the_phases_saves_a_valid_draft_plan_and_reaches_planning(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    llm: ScriptedLLM,
    redis: Redis,
    app_sessions: Any,
) -> None:
    run = await planning_run(engine, app_sessions)
    llm.add(propose(), save_plan())
    await run_job(ctx, run)

    await _review(engine, ctx, run, PHASES)

    plans = await stored_plans(engine, run)
    assert [(p["status"], p["version"]) for p in plans] == [("draft", 1)]
    assert await stored_phases(engine, run) == ["Foundations", "Core", "Launch"]
    assert await stored_tasks(engine, run) == [
        ("Foundations", "Task a", 3),
        ("Core", "Task b", 5),
        ("Launch", "Task c", 2),
    ]
    assert await stored_dep_count(engine, run) == 2
    assert await idea_stage(engine, run) == "exported"  # the stubs after the Planner finish
    assert "planner" in finished(await events_of(redis, run))
    assert llm.calls == 2


async def test_the_edited_phases_are_the_phases_of_the_plan(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, app_sessions: Any
) -> None:
    run = await planning_run(engine, app_sessions)
    edited = [
        {"name": "Launch", "goal": "Ship it first.", "exit_criteria": "Live."},
        {"name": "Research", "goal": "Talk to users.", "exit_criteria": "10 calls."},
    ]
    llm.add(propose(), save_plan([task("a", 0), task("b", 1, 2, ("a",))]))
    await run_job(ctx, run)

    await _review(engine, ctx, run, edited)

    assert await stored_phases(engine, run) == ["Launch", "Research"]
    assert [phase for phase, _, _ in await stored_tasks(engine, run)] == ["Launch", "Research"]
    assert "Research" in llm.shown(1)


async def test_a_dependency_cycle_is_refused_with_the_tasks_named_then_fixed(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, app_sessions: Any
) -> None:
    run = await planning_run(engine, app_sessions)
    looping = [task("a", 0, 3, ("b",)), task("b", 1, 3, ("a",))]
    llm.add(propose(), save_plan(looping), save_plan())
    await run_job(ctx, run)

    await _review(engine, ctx, run, PHASES)

    seen = llm.shown(2)
    assert "wait on each other in a loop: " in seen
    assert len(await stored_plans(engine, run)) == 1
    assert len(await stored_tasks(engine, run)) == len(TASKS)


async def test_a_task_without_an_issue_brief_is_refused_with_the_missing_sections_then_fixed(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, app_sessions: Any
) -> None:
    run = await planning_run(engine, app_sessions)
    thin = {**task("a", 0), "description": "Do a. Done when a works."}
    llm.add(propose(), save_plan([thin]), save_plan())
    await run_job(ctx, run)

    await _review(engine, ctx, run, PHASES)

    seen = llm.shown(2)
    assert "`a` lacks `## Goal`, `## Requirements`, `## Acceptance criteria`" in seen
    assert len(await stored_plans(engine, run)) == 1
    assert len(await stored_tasks(engine, run)) == len(TASKS)


async def test_an_estimate_above_eight_is_refused_with_the_split_hint(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, app_sessions: Any
) -> None:
    run = await planning_run(engine, app_sessions)
    llm.add(propose(), save_plan([task("a", 0, 13)]), save_plan([task("a", 0, 8), task("b", 0, 5)]))
    await run_job(ctx, run)

    await _review(engine, ctx, run, PHASES)

    assert "Split work above 8" in llm.shown(2)
    assert [e for _, _, e in await stored_tasks(engine, run)] == [8, 5]


async def test_two_refused_plans_fail_the_run_and_store_nothing(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, app_sessions: Any
) -> None:
    run = await planning_run(engine, app_sessions)
    llm.add(propose(), save_plan([task("a", 0, 13)]), save_plan([task("a", 7, 3)]))
    await run_job(ctx, run)

    await _review(engine, ctx, run, PHASES)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "plan.invalid_submission"
    assert await stored_plans(engine, run) == []
    assert await idea_stage(engine, run) == "spec_confirmed"


async def test_an_empty_task_list_is_refused_then_fixed(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, app_sessions: Any
) -> None:
    run = await planning_run(engine, app_sessions)
    llm.add(propose(), save_plan([]), save_plan())
    await run_job(ctx, run)

    await _review(engine, ctx, run, PHASES)

    assert "needs at least one task" in llm.shown(2)
    assert len(await stored_plans(engine, run)) == 1


async def test_saving_before_the_phases_are_reviewed_is_a_refusal_the_model_can_fix(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, app_sessions: Any
) -> None:
    run = await planning_run(engine, app_sessions)
    llm.add(save_plan(), propose())

    await run_job(ctx, run)

    assert "Call propose_phases first" in llm.shown(1)
    assert (await _pending(engine, run))["type"] == "phase_review"


async def test_a_loop_that_ends_without_a_plan_fails_the_run(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, app_sessions: Any
) -> None:
    run = await planning_run(engine, app_sessions)
    llm.add(propose(), Reply(text="Here is my plan in words."))
    await run_job(ctx, run)

    await _review(engine, ctx, run, PHASES)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "plan.invalid_submission"


async def test_a_bad_phase_proposal_is_refused_before_the_user_is_asked(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, app_sessions: Any
) -> None:
    run = await planning_run(engine, app_sessions)
    llm.add(propose(PHASES[:2]), propose())

    await run_job(ctx, run)

    assert "Propose 3 to 7 phases" in llm.shown(1)
    assert (await _pending(engine, run))["type"] == "phase_review"


async def test_resuming_makes_no_second_phase_proposal_and_saves_one_plan(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, app_sessions: Any
) -> None:
    run = await planning_run(engine, app_sessions)
    llm.add(propose(), save_plan())
    await run_job(ctx, run)
    first = await _pending(engine, run)

    await _review(engine, ctx, run, PHASES)

    assert llm.calls == 2  # one proposal, one save; none repeated by the resume
    assert first["phases"] == [{**p} for p in PHASES]
    assert len(await stored_plans(engine, run)) == 1


async def test_an_existing_plan_for_the_confirmed_spec_skips_the_model(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    llm: ScriptedLLM,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    run = await planning_run(engine, app_sessions)
    await save_existing_plan(engine, app_sessions, run)
    before = (await stored_plans(engine, run))[0]

    await run_job(ctx, run)

    assert llm.calls == 0
    assert (await run_row(engine, run)).status == "succeeded"
    assert [p["id"] for p in await stored_plans(engine, run)] == [before["id"]]
    assert await idea_stage(engine, run) == "exported"


async def test_a_run_without_a_confirmed_spec_fails(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, app_sessions: Any
) -> None:
    run = await planning_run(engine, app_sessions, confirm=False)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ideas.ideas SET stage = 'spec_confirmed' WHERE id = "
                "(SELECT idea_id FROM ideas.workflow_runs WHERE id = :id)"
            ),
            {"id": run.run_id},
        )

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "spec.not_found"
    assert llm.calls == 0


async def test_the_planner_prompt_asks_for_non_engineering_tasks_for_other_ideas() -> None:
    prompt = load_prompt("planner")

    assert "not software" in prompt and "non-engineering" in prompt


LINEAR_READ_TOOLS = {"list_teams", "list_projects", "list_issues"}
LINEAR_SERVER_TOOLS = (*LINEAR_READ_TOOLS, "save_issue", "save_project", "delete_issue")


def _tool_names(llm: ScriptedLLM) -> set[str]:
    return {t["function"]["name"] for t in llm.bodies[0]["tools"]}


async def test_a_connected_linear_gives_the_planner_its_read_tools_only(
    engine: AsyncEngine,
    llm: ScriptedLLM,
    redis: Redis,
    checkpointer: AsyncPostgresSaver,
    app_sessions: Any,
) -> None:
    async with FakeLinear(tools=LINEAR_SERVER_TOOLS).running() as linear:
        ctx = job_ctx(
            redis,
            app_sessions,
            llm=llm,
            planner=True,
            oauth=oauth_client(linear),
            mcp=mcp_client(linear),
        )
        run = await planning_run(engine, app_sessions)
        await connect_workspace(engine, app_sessions, run.workspace_id, linear)
        llm.add(propose())

        await run_job(ctx, run)

    assert _tool_names(llm) == {"propose_phases", "save_plan", *LINEAR_READ_TOOLS}
    assert (await run_row(engine, run)).status == "awaiting_user"


async def test_an_expired_linear_leaves_the_planner_working_with_a_notice(
    engine: AsyncEngine,
    llm: ScriptedLLM,
    redis: Redis,
    checkpointer: AsyncPostgresSaver,
    app_sessions: Any,
) -> None:
    async with FakeLinear(tools=LINEAR_SERVER_TOOLS).running() as linear:
        ctx = job_ctx(
            redis,
            app_sessions,
            llm=llm,
            planner=True,
            oauth=oauth_client(linear),
            mcp=mcp_client(linear),
        )
        run = await planning_run(engine, app_sessions)
        await connect_workspace(engine, app_sessions, run.workspace_id, linear, status="expired")
        llm.add(propose())

        await run_job(ctx, run)

    assert _tool_names(llm) == {"propose_phases", "save_plan"}
    notices = [e for e in await events_of(redis, run) if e.type is RunEventType.NOTICE]
    assert [n.data["code"] for n in notices] == ["mcp.expired"]
    assert (await run_row(engine, run)).status == "awaiting_user"


async def test_a_run_pausing_on_the_phase_review_resumes_with_linear_tools_loaded(
    engine: AsyncEngine,
    llm: ScriptedLLM,
    redis: Redis,
    checkpointer: AsyncPostgresSaver,
    app_sessions: Any,
) -> None:
    async with FakeLinear(tools=LINEAR_SERVER_TOOLS).running() as linear:
        ctx = job_ctx(
            redis,
            app_sessions,
            llm=llm,
            planner=True,
            oauth=oauth_client(linear),
            mcp=mcp_client(linear),
        )
        run = await planning_run(engine, app_sessions)
        await connect_workspace(engine, app_sessions, run.workspace_id, linear)
        llm.add(propose(), save_plan())
        await run_job(ctx, run)

        await _review(engine, ctx, run, PHASES)

    assert (await stored_plans(engine, run))[0]["status"] == "draft"
    assert (await run_row(engine, run)).status == "succeeded"
