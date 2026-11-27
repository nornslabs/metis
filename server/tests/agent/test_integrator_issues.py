"""The Integrator's last step (SHIP-254): labels, one Linear issue per task, blocked-by links,
and the end of the export.

Seam: the ``run_graph`` job with the real Integrator node, on real Postgres as ``metis_app``, real
Redis and the real checkpointer, and Linear faked in-process (``tests/helpers/fake_linear``). A
"retry" is a new run on the same idea that is approved again, as the web starts it. Tests check
what Linear holds, what Metis stored (refs, export job, stage, outbox) and what the user sees
(events, run status), not internals.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.core.events import RunEventType
from metis.modules import planning
from tests.agent.export_helpers import (
    TOOLS,
    approval,
    export_ctx,
    export_jobs,
    export_run,
    external_refs,
    local_ids,
    next_run,
    outbox_count,
    reopen_idea,
    rerun_node,
)
from tests.agent.linear_helpers import connect_workspace
from tests.agent.planner_helpers import idea_of
from tests.agent.run_job_helpers import (
    QueuedRun,
    checkpoint_values,
    events_of,
    idea_stage,
    run_job,
    run_row,
)
from tests.helpers.fake_linear import FakeLinear

# The writes before the first issue: the project, three milestones and the one label that is
# missing in Linear ("Frontend").
WRITES_BEFORE_ISSUES = 5


def _plan() -> planning.PlanInput:
    """Three phases; ``b`` is a sub-task of ``a`` and blocked by it; ``c`` is blocked by ``b``."""
    phases = tuple(
        planning.PhaseInput(name=name, goal=f"Do {name}.", exit_criteria=f"{name} done.")
        for name in ("Foundations", "Core", "Launch")
    )
    tasks = (
        planning.TaskInput(
            key="a",
            phase=0,
            title="Task a",
            description="Build the thing.\n\n- step one\n- step two",
            estimate=3,
            labels=("backend",),
        ),
        planning.TaskInput(
            key="b",
            phase=1,
            title="Task b",
            estimate=5,
            labels=("backend", "Frontend"),
            parent_key="a",
        ),
        planning.TaskInput(key="c", phase=2, title="Task c", estimate=2),
    )
    deps = (
        planning.DepInput(task_key="b", blocked_by_key="a"),
        planning.DepInput(task_key="c", blocked_by_key="b"),
    )
    return planning.PlanInput(phases=phases, tasks=tasks, deps=deps)


@pytest_asyncio.fixture
async def linear() -> AsyncIterator[FakeLinear]:
    async with FakeLinear(tools=TOOLS).running() as fake:
        yield fake


@pytest.fixture
def ctx(
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
    linear: FakeLinear,
) -> dict[str, Any]:
    return export_ctx(redis, app_sessions, linear)


async def _export(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    ctx: dict[str, Any],
    linear: FakeLinear,
) -> QueuedRun:
    """A run taken to the approval prompt (team ``team-2``) and approved."""
    run = await export_run(engine, sessions, plan_input=_plan())
    await connect_workspace(engine, sessions, run.workspace_id, linear)
    await run_job(ctx, run)
    await run_job(ctx, run, resume={"team_id": "team-2"})
    await run_job(ctx, run, resume=await approval(engine, run, approved=True))
    return run


async def _export_again(engine: AsyncEngine, ctx: dict[str, Any], run: QueuedRun) -> QueuedRun:
    """Export the same idea again: a new run, a new preview, a new approval."""
    await reopen_idea(engine, run)
    again = await next_run(engine, run)
    await run_job(ctx, again)
    await run_job(ctx, again, resume=await approval(engine, again, approved=True))
    return again


def _issue(linear: FakeLinear, title: str) -> dict[str, Any]:
    [issue] = [i for i in linear.issues.values() if i["title"] == title]
    return issue


def _id_of(linear: FakeLinear, title: str) -> str:
    [key] = [k for k, i in linear.issues.items() if i["title"] == title]
    return key


async def _issue_creates(linear: FakeLinear) -> int:
    return sum(1 for name, args in linear.tool_calls if name == "save_issue" and not args["id"])


# --------------------------------------------------------------------- first export
async def test_every_task_becomes_an_issue_under_the_milestone_of_its_phase(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    await _export(engine, app_sessions, ctx, linear)

    assert [i["title"] for i in linear.issues.values()] == ["Task a", "Task b", "Task c"]
    milestones = {i["title"]: i["milestone"] for i in linear.issues.values()}
    assert milestones == {"Task a": "milestone-1", "Task b": "milestone-2", "Task c": "milestone-3"}
    assert {i["project"] for i in linear.issues.values()} == {"project-1"}
    assert {i["team"] for i in linear.issues.values()} == {"team-2"}
    assert _issue(linear, "Task a")["estimate"] == 3
    assert _issue(linear, "Task b")["estimate"] == 5


async def test_an_issue_description_keeps_the_task_text_and_ends_with_the_metis_footer(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _export(engine, app_sessions, ctx, linear)

    description = _issue(linear, "Task a")["description"]
    assert description.startswith("Build the thing.\n\n- step one\n- step two")
    assert description.endswith(
        f"Created by [Metis](http://localhost:3000/ideas/{await idea_of(engine, run)})"
    )


async def test_a_sub_task_is_created_under_its_parent_issue(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    await _export(engine, app_sessions, ctx, linear)

    assert _issue(linear, "Task b")["parent"] == _id_of(linear, "Task a")
    assert _issue(linear, "Task a")["parent"] == ""


async def test_dependencies_become_blocked_by_links_between_the_right_issues(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    await _export(engine, app_sessions, ctx, linear)

    assert _issue(linear, "Task a")["blocked_by"] == []
    assert _issue(linear, "Task b")["blocked_by"] == [_id_of(linear, "Task a")]
    assert _issue(linear, "Task c")["blocked_by"] == [_id_of(linear, "Task b")]


async def test_the_first_export_saves_a_ref_for_every_task_and_ends_the_job(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _export(engine, app_sessions, ctx, linear)

    refs = await external_refs(engine, run)
    task_ids = await local_ids(engine, run, "tasks")
    assert [refs[("task", task_id)] for task_id in task_ids] == ["issue-1", "issue-2", "issue-3"]
    [job] = await export_jobs(engine, run)
    assert job["status"] == "succeeded"
    assert job["summary"]["result"]["created"] == 7
    assert job["summary"]["result"]["updated"] == 0
    assert job["summary"]["result"]["links"] == 2
    assert job["summary"]["result"]["failed"] == []
    assert job["summary"]["result"]["project_url"] == "https://linear.app/project/project-1"


async def test_a_finished_export_moves_the_idea_to_exported_and_clears_the_approval(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear, redis: Redis
) -> None:
    run = await _export(engine, app_sessions, ctx, linear)

    assert (await run_row(engine, run)).status == "succeeded"
    assert await idea_stage(engine, run) == "exported"
    assert (await checkpoint_values(run))["pending_approval"] is None
    assert await outbox_count(engine, run, "ExportFinished") == 1
    [finished] = [e for e in await events_of(redis, run) if e.type is RunEventType.EXPORT_FINISHED]
    assert finished.data == {
        "project_url": "https://linear.app/project/project-1",
        "created": 7,
        "updated": 0,
        "links": 2,
    }


async def test_progress_counts_the_issues_and_one_links_item(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear, redis: Redis
) -> None:
    run = await _export(engine, app_sessions, ctx, linear)

    progress = [
        e.data for e in await events_of(redis, run) if e.type is RunEventType.EXPORT_PROGRESS
    ]
    assert [(p["item"], p["done"], p["total"]) for p in progress[4:]] == [
        ("issue", 5, 8),
        ("issue", 6, 8),
        ("issue", 7, 8),
        ("links", 8, 8),
    ]
    assert [p["name"] for p in progress[4:7]] == ["Task a", "Task b", "Task c"]


# ------------------------------------------------------------------------- labels
async def test_labels_that_are_missing_in_linear_are_created_once_and_existing_ones_are_not(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    await _export(engine, app_sessions, ctx, linear)

    assert linear.labels_created == ["Frontend"]  # "backend" already existed
    assert _issue(linear, "Task b")["labels"] == ["backend", "Frontend"]
    assert _issue(linear, "Task c")["labels"] == []


async def test_a_label_that_cannot_be_created_is_left_off_and_the_user_is_told(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear, redis: Redis
) -> None:
    linear.fail_label_create = True

    run = await _export(engine, app_sessions, ctx, linear)

    assert (await run_row(engine, run)).status == "succeeded"
    assert _issue(linear, "Task b")["labels"] == ["backend"]
    notices = [e.data["code"] for e in await events_of(redis, run) if e.type is RunEventType.NOTICE]
    assert notices == ["export.labels_skipped"]


async def test_without_the_label_tools_the_issues_are_made_without_labels(
    engine: AsyncEngine, app_sessions: Any, redis: Redis, checkpointer: AsyncPostgresSaver
) -> None:
    tools = tuple(t for t in TOOLS if t not in ("list_issue_labels", "create_issue_label"))
    async with FakeLinear(tools=tools).running() as fake:
        ctx = export_ctx(redis, app_sessions, fake)

        run = await _export(engine, app_sessions, ctx, fake)

    assert (await run_row(engine, run)).status == "succeeded"
    assert {tuple(i["labels"]) for i in fake.issues.values()} == {()}
    assert len(fake.issues) == 3


# ------------------------------------------------------------------ an export again
async def test_exporting_again_updates_the_issues_and_creates_nothing(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _export(engine, app_sessions, ctx, linear)
    before = await external_refs(engine, run)
    creates = await _issue_creates(linear)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE planning.tasks SET title = 'Task a (renamed)' WHERE title = 'Task a'")
        )

    again = await _export_again(engine, ctx, run)

    assert (await run_row(engine, again)).status == "succeeded"
    assert await _issue_creates(linear) == creates
    assert len(linear.issues) == 3
    assert "Task a (renamed)" in {i["title"] for i in linear.issues.values()}
    assert await external_refs(engine, run) == before
    assert _issue(linear, "Task c")["blocked_by"] == [_id_of(linear, "Task b")]


async def test_running_a_finished_export_again_writes_nothing_and_no_second_event(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    app_sessions: Any,
    linear: FakeLinear,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = await _export(engine, app_sessions, ctx, linear)
    calls = len(linear.tool_calls)

    update = await rerun_node(engine, app_sessions, redis, linear, run, monkeypatch, reopen=False)

    assert update["export_state"] == "approved"
    assert update["pending_approval"] is None
    assert update["stage"] == "exported"
    assert len(linear.tool_calls) == calls
    assert await outbox_count(engine, run, "ExportFinished") == 1
    assert len(
        [e for e in await events_of(redis, run) if e.type is RunEventType.EXPORT_FINISHED]
    ) == 1
    assert [j["status"] for j in await export_jobs(engine, run)] == ["succeeded"]


# ---------------------------------------------------------------- failures, partial
async def test_a_failed_issue_is_skipped_with_what_depends_on_it_and_the_export_ends_partial(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    linear.fail_issue_titles = {"Task b"}

    run = await _export(engine, app_sessions, ctx, linear)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "export.partial"
    assert sorted(i["title"] for i in linear.issues.values()) == ["Task a", "Task c"]
    [job] = await export_jobs(engine, run)
    assert job["status"] == "partial"
    failed = job["summary"]["result"]["failed"]
    assert [(f["kind"], f["name"]) for f in failed] == [
        ("issue", "Task b"),
        ("link", "Task b"),
        ("link", "Task c"),
    ]
    assert [f["reason"] for f in failed[1:]] == ["skipped", "skipped"]
    assert failed[0]["reason"] != "skipped"  # Linear refused it
    assert await idea_stage(engine, run) == "planning"
    task_ids = await local_ids(engine, run, "tasks")
    refs = await external_refs(engine, run)
    assert [("task", task_id) in refs for task_id in task_ids] == [True, False, True]
    assert await outbox_count(engine, run, "ExportFinished") == 0


async def test_a_sub_task_whose_parent_failed_is_not_created_detached(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    linear.fail_issue_titles = {"Task a"}  # the parent of "Task b"

    await _export(engine, app_sessions, ctx, linear)

    assert [i["title"] for i in linear.issues.values()] == ["Task c"]


async def test_a_new_export_after_a_partial_one_creates_only_what_is_missing(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    linear.fail_issue_titles = {"Task b"}
    run = await _export(engine, app_sessions, ctx, linear)
    linear.fail_issue_titles = set()
    creates = await _issue_creates(linear)

    again = await _export_again(engine, ctx, run)

    assert (await run_row(engine, again)).status == "succeeded"
    assert await _issue_creates(linear) == creates + 1  # only "Task b"
    assert len(linear.issues) == 3
    assert _issue(linear, "Task b")["blocked_by"] == [_id_of(linear, "Task a")]
    assert _issue(linear, "Task c")["blocked_by"] == [_id_of(linear, "Task b")]
    assert await idea_stage(engine, again) == "exported"
    assert [j["status"] for j in await export_jobs(engine, again)] == ["succeeded"]


async def test_a_connection_that_expires_midway_keeps_what_was_saved_and_ends_partial(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    linear.expire_after_writes = WRITES_BEFORE_ISSUES + 1  # one issue is saved, then it lapses

    run = await _export(engine, app_sessions, ctx, linear)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "mcp.expired"
    assert [j["status"] for j in await export_jobs(engine, run)] == ["partial"]
    assert [i["title"] for i in linear.issues.values()] == ["Task a"]
    task_ids = await local_ids(engine, run, "tasks")
    assert ("task", task_ids[0]) in await external_refs(engine, run)  # committed before the lapse
    assert await idea_stage(engine, run) == "planning"


async def test_an_export_that_saved_nothing_ends_failed_not_partial(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    linear.fail_save_at = 1  # the project itself

    run = await _export(engine, app_sessions, ctx, linear)

    assert [j["status"] for j in await export_jobs(engine, run)] == ["failed"]
    assert linear.issues == {}
    assert await outbox_count(engine, run, "ExportFinished") == 0


# ---------------------------------------------------------------------- the gates
async def test_a_declined_export_creates_no_issue_and_no_label(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await export_run(engine, app_sessions, plan_input=_plan())
    await connect_workspace(engine, app_sessions, run.workspace_id, linear)
    await run_job(ctx, run)
    await run_job(ctx, run, resume={"team_id": "team-2"})

    await run_job(ctx, run, resume=await approval(engine, run, approved=False))

    assert linear.write_calls == []
    assert linear.issues == {} and linear.labels_created == []
    assert await idea_stage(engine, run) == "planning"
    assert await outbox_count(engine, run, "ExportFinished") == 0


async def test_no_event_carries_a_token_or_the_task_text(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear, redis: Redis
) -> None:
    run = await _export(engine, app_sessions, ctx, linear)

    dump = " ".join(str(e.data) for e in await events_of(redis, run))

    for token in linear.mcp_tokens_seen:
        assert token is None or token not in dump
    assert "step one" not in dump
