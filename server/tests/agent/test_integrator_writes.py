"""The Integrator's second step (SHIP-253): the Linear project and one milestone per phase.
(SHIP-254 adds the issues; their own tests are in ``test_integrator_issues``.)

Seam: the ``run_graph`` job with the real Integrator node, on real Postgres as ``metis_app``, real
Redis and the real checkpointer, and Linear faked in-process (``tests/helpers/fake_linear``). A
retry of a stopped export is the node run again on the same run (what the job does after a crash:
the recorded approval is found and the writes carry on). Tests check what Linear holds, what Metis
stored (refs, export job) and what the user sees (events, run status), not internals.
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
from tests.agent.export_helpers import (
    TOOLS,
    approval,
    bump_plan_version,
    export_ctx,
    export_jobs,
    export_run,
    external_refs,
    local_ids,
    rerun_node,
)
from tests.agent.linear_helpers import connect_workspace
from tests.agent.planner_helpers import idea_of
from tests.agent.run_job_helpers import QueuedRun, events_of, run_job, run_row
from tests.helpers.fake_linear import FakeLinear

PHASES = ["Phase 1 — Foundations", "Phase 2 — Core", "Phase 3 — Launch"]


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


async def _approved(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    ctx: dict[str, Any],
    linear: FakeLinear,
    *,
    answer: bool = True,
) -> QueuedRun:
    """A run taken to the approval prompt (team ``team-2``) and answered."""
    run = await export_run(engine, sessions)
    await connect_workspace(engine, sessions, run.workspace_id, linear)
    await run_job(ctx, run)
    await run_job(ctx, run, resume={"team_id": "team-2"})
    if answer:
        await run_job(ctx, run, resume=await approval(engine, run, approved=True))
    return run


async def _retry(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    redis: Redis,
    linear: FakeLinear,
    run: QueuedRun,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    return await rerun_node(engine, sessions, redis, linear, run, monkeypatch)


async def _idea_title(engine: AsyncEngine, run: QueuedRun) -> str:
    async with engine.connect() as conn:
        value = await conn.scalar(
            text("SELECT title FROM ideas.ideas WHERE id = :id"), {"id": await idea_of(engine, run)}
        )
    return str(value)


def _creates(linear: FakeLinear, tool: str) -> int:
    """How many ``tool`` calls were creates (no Linear id in the arguments)."""
    return sum(1 for name, args in linear.tool_calls if name == tool and not args["id"])


# --------------------------------------------------------------------- first export
async def test_the_first_export_creates_the_project_and_one_milestone_per_phase(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _approved(engine, app_sessions, ctx, linear)

    assert (await run_row(engine, run)).status == "succeeded"
    [project] = linear.projects.values()
    assert project["name"] == await _idea_title(engine, run)
    assert project["teams"] == ["team-2"]
    assert "Leads get lost." in project["description"]
    assert "Plan version 1." in project["description"]
    milestones = list(linear.milestones.values())
    assert [m["name"] for m in milestones] == PHASES
    assert [m["sort_order"] for m in milestones] == [0, 1, 2]
    assert {m["project"] for m in milestones} == {"project-1"}
    assert "Do Foundations." in milestones[0]["description"]
    assert "Foundations done." in milestones[0]["description"]


async def test_the_first_export_saves_a_ref_for_the_idea_and_every_phase(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _approved(engine, app_sessions, ctx, linear)

    refs = await external_refs(engine, run)
    phase_ids = await local_ids(engine, run, "phases")
    assert refs[("idea", await idea_of(engine, run))] == "project-1"
    assert [refs[("phase", phase_id)] for phase_id in phase_ids] == [
        "milestone-1",
        "milestone-2",
        "milestone-3",
    ]
    assert len(refs) == 4 + 3  # the idea, its phases and its tasks
    assert [j["status"] for j in await export_jobs(engine, run)] == ["succeeded"]


async def test_one_progress_event_is_published_per_item_in_order(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear, redis: Redis
) -> None:
    run = await _approved(engine, app_sessions, ctx, linear)

    progress = [
        e.data for e in await events_of(redis, run) if e.type is RunEventType.EXPORT_PROGRESS
    ]
    assert [(p["item"], p["done"], p["total"]) for p in progress] == [
        ("project", 1, 8),
        ("milestone", 2, 8),
        ("milestone", 3, 8),
        ("milestone", 4, 8),
        ("issue", 5, 8),
        ("issue", 6, 8),
        ("issue", 7, 8),
        ("links", 8, 8),
    ]
    assert {p["action"] for p in progress[:7]} == {"create"}
    assert [p["name"] for p in progress[1:4]] == PHASES


# ----------------------------------------------------------------------- a re-run
async def test_running_the_export_again_updates_and_never_duplicates(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    app_sessions: Any,
    linear: FakeLinear,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = await _approved(engine, app_sessions, ctx, linear)
    before = await external_refs(engine, run)
    creates = (_creates(linear, "save_project"), _creates(linear, "save_milestone"))

    await _retry(engine, app_sessions, redis, linear, run, monkeypatch)

    assert (_creates(linear, "save_project"), _creates(linear, "save_milestone")) == creates
    assert len(linear.projects) == 1 and len(linear.milestones) == 3
    assert len(linear.issues) == 3 and _creates(linear, "save_issue") == 3
    assert await external_refs(engine, run) == before
    assert len(await export_jobs(engine, run)) == 1


async def test_a_renamed_idea_and_an_edited_phase_reach_linear_on_the_next_run(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    app_sessions: Any,
    linear: FakeLinear,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = await _approved(engine, app_sessions, ctx, linear)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE ideas.ideas SET title = 'Renamed idea' WHERE id = :id"),
            {"id": await idea_of(engine, run)},
        )
        await conn.execute(
            text(
                "UPDATE planning.phases SET name = 'Basics' WHERE id = "
                "(SELECT ph.id FROM planning.phases ph JOIN planning.plans p ON p.id = ph.plan_id "
                "WHERE p.idea_id = :idea ORDER BY ph.position LIMIT 1)"
            ),
            {"idea": await idea_of(engine, run)},
        )

    await _retry(engine, app_sessions, redis, linear, run, monkeypatch)

    assert linear.projects["project-1"]["name"] == "Renamed idea"
    assert linear.milestones["milestone-1"]["name"] == "Phase 1 — Basics"
    assert len(linear.milestones) == 3


# ------------------------------------------------------------------ stopped midway
async def test_an_export_that_stopped_midway_creates_only_the_missing_milestones(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    app_sessions: Any,
    linear: FakeLinear,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    linear.fail_save_at = 3  # the project and the first milestone are saved, the second fails
    run = await _approved(engine, app_sessions, ctx, linear)
    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "provider.upstream_error"
    saved = await external_refs(engine, run)
    assert sorted(saved.values()) == ["milestone-1", "project-1"]  # committed before the failure
    assert len(linear.milestones) == 1
    assert [j["status"] for j in await export_jobs(engine, run)] == ["partial"]

    await _retry(engine, app_sessions, redis, linear, run, monkeypatch)

    assert [m["name"] for m in linear.milestones.values()] == PHASES
    assert len(linear.projects) == 1
    assert _creates(linear, "save_project") == 1
    # 3 phases plus the one attempt that failed: the retry did not re-create the saved milestone.
    assert _creates(linear, "save_milestone") == len(PHASES) + 1
    assert len(await external_refs(engine, run)) == 4 + 3
    assert [j["status"] for j in await export_jobs(engine, run)] == ["succeeded"]


async def test_a_failing_project_save_leaves_no_ref_and_the_export_failed(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    linear.fail_save_at = 1

    run = await _approved(engine, app_sessions, ctx, linear)

    assert (await run_row(engine, run)).status == "failed"
    assert await external_refs(engine, run) == {}
    assert linear.milestones == {}
    assert [j["status"] for j in await export_jobs(engine, run)] == ["failed"]


async def test_an_answer_with_no_id_is_a_failure_and_saves_no_ref(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    linear.save_without_id = True

    run = await _approved(engine, app_sessions, ctx, linear)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "provider.upstream_error"
    assert await external_refs(engine, run) == {}


# ---------------------------------------------------------------------- the gates
async def test_a_plan_changed_after_the_preview_stops_the_export_before_any_write(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _approved(engine, app_sessions, ctx, linear, answer=False)
    await bump_plan_version(engine, run)

    await run_job(ctx, run, resume=await approval(engine, run, approved=True, plan_version=1))

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "export.plan_changed"
    assert linear.write_calls == []
    assert await external_refs(engine, run) == {}
    assert [j["status"] for j in await export_jobs(engine, run)] == ["approved"]


async def test_an_approval_that_names_no_plan_version_stops_before_any_write(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _approved(engine, app_sessions, ctx, linear, answer=False)
    answer = await approval(engine, run, approved=True)
    del answer["plan_version"]

    await run_job(ctx, run, resume=answer)

    row = await run_row(engine, run)
    assert row.error is not None and row.error["code"] == "export.plan_changed"
    assert linear.write_calls == []


async def test_a_declined_export_writes_nothing_to_linear(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _approved(engine, app_sessions, ctx, linear, answer=False)

    await run_job(ctx, run, resume=await approval(engine, run, approved=False))

    assert (await run_row(engine, run)).status == "succeeded"
    assert linear.write_calls == []
    assert await external_refs(engine, run) == {}
    assert [j["status"] for j in await export_jobs(engine, run)] == ["declined"]


async def test_no_event_carries_a_token_or_a_call_argument(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear, redis: Redis
) -> None:
    run = await _approved(engine, app_sessions, ctx, linear)

    dump = " ".join(str(e.data) for e in await events_of(redis, run))

    for token in linear.mcp_tokens_seen:
        assert token is None or token not in dump
    assert "Leads get lost." not in dump
    assert "Do Foundations." not in dump
