"""The Integrator's first step (SHIP-252): choose the Linear team, preview, approve.

Seam: the ``run_graph`` job with the real Integrator node, on real Postgres as ``metis_app``,
real Redis and the real checkpointer, and Linear faked in-process (``tests/helpers/fake_linear``).
The two interrupts are answered the way the resume route does: the job is called with
``resume``. Tests check what the user sees (interrupt payloads, run status, stage), what is
stored (export job, settings, plan) and what Linear saw (never a write).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.specialists.integrator import build_integrator
from metis.agent.state import initial_state
from metis.core.events import RunEventType
from metis.modules.ideas import Stage
from tests.agent.export_helpers import (
    TOOLS,
    add_refs,
    approval,
    export_ctx,
    export_jobs,
    export_run,
    local_ids,
    plan_status,
    save_team,
    saved_team,
)
from tests.agent.linear_helpers import connect_workspace, mcp_client, oauth_client
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
from tests.modules.scoring.scoring_helpers import in_workspace


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


async def _ready(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    linear: FakeLinear,
    **kwargs: Any,
) -> QueuedRun:
    run = await export_run(engine, sessions, **kwargs)
    await connect_workspace(engine, sessions, run.workspace_id, linear)
    return run


async def _pending(engine: AsyncEngine, run: QueuedRun) -> dict[str, Any]:
    pending = (await run_row(engine, run)).pending_interrupt
    assert pending is not None
    return pending


async def _to_approval(
    engine: AsyncEngine, ctx: dict[str, Any], run: QueuedRun, team_id: str = "team-2"
) -> dict[str, Any]:
    """Run to the approval prompt, picking ``team_id`` when asked; the pending interrupt."""
    await run_job(ctx, run)
    if (await _pending(engine, run))["type"] == "choose_team":
        await run_job(ctx, run, resume={"team_id": team_id})
    return await _pending(engine, run)


# ------------------------------------------------------------------------ team
async def test_with_no_saved_team_the_run_asks_which_team(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _ready(engine, app_sessions, linear)

    await run_job(ctx, run)

    pending = await _pending(engine, run)
    assert pending["type"] == "choose_team"
    assert [t["name"] for t in pending["teams"]] == ["Product", "Platform"]
    assert pending["saved_team_id"] is None
    assert (await run_row(engine, run)).status == "awaiting_user"


async def test_a_saved_team_that_is_still_there_is_not_asked_again(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _ready(engine, app_sessions, linear)
    await save_team(engine, run, "team-1")

    await run_job(ctx, run)

    pending = await _pending(engine, run)
    assert pending["type"] == "export_approval"
    assert pending["preview"]["team"] == {"id": "team-1", "name": "Product"}


async def test_a_saved_team_that_is_gone_is_asked_again_and_says_so(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _ready(engine, app_sessions, linear)
    await save_team(engine, run, "team-deleted")

    await run_job(ctx, run)

    pending = await _pending(engine, run)
    assert (pending["type"], pending["saved_team_id"]) == ("choose_team", "team-deleted")


async def test_linear_with_no_teams_fails_the_run_with_a_clear_code(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    linear.teams = []
    run = await _ready(engine, app_sessions, linear)

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "export.no_linear_team"


# --------------------------------------------------------------------- preview
async def test_the_preview_counts_match_the_plan(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _ready(engine, app_sessions, linear)

    pending = await _to_approval(engine, ctx, run)

    preview = pending["preview"]
    assert pending["type"] == "export_approval"
    assert preview["team"] == {"id": "team-2", "name": "Platform"}
    assert preview["project"] == {"name": "Pocket CRM", "action": "create"}
    assert [m["name"] for m in preview["milestones"]["items"]] == [
        "Foundations",
        "Core",
        "Launch",
    ]
    assert (preview["milestones"]["total"], preview["milestones"]["create"]) == (3, 3)
    assert (preview["issues"]["total"], preview["issues"]["create"]) == (3, 3)
    assert preview["blocked_by_links"] == 2
    assert preview["labels"]["items"] == [
        {"name": "Frontend", "exists": False},
        {"name": "backend", "exists": True},
    ]


async def test_items_already_exported_show_as_updates(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _ready(engine, app_sessions, linear)
    await add_refs(engine, run, "idea", [await idea_of(engine, run)])
    await add_refs(engine, run, "phase", (await local_ids(engine, run, "phases"))[:1])
    await add_refs(engine, run, "task", (await local_ids(engine, run, "tasks"))[:2])

    preview = (await _to_approval(engine, ctx, run))["preview"]

    assert preview["project"]["action"] == "update"
    assert (preview["milestones"]["create"], preview["milestones"]["update"]) == (2, 1)
    assert (preview["issues"]["create"], preview["issues"]["update"]) == (1, 2)
    assert [m["action"] for m in preview["milestones"]["items"]] == ["update", "create", "create"]


async def test_labels_are_left_unchecked_when_linear_has_no_label_tool(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, redis: Redis
) -> None:
    async with FakeLinear(tools=("list_teams", "save_project", "save_issue")).running() as fake:
        run = await _ready(engine, app_sessions, fake)
        ctx = export_ctx(redis, app_sessions, fake)

        preview = (await _to_approval(engine, ctx, run))["preview"]

    assert {label["exists"] for label in preview["labels"]["items"]} == {None}


async def test_an_idea_with_no_plan_fails_with_no_plan(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _ready(engine, app_sessions, linear, plan=False)

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "export.no_plan"


# -------------------------------------------------------------------- approval
async def test_approving_records_who_and_when_writes_the_project_and_ends_the_run_at_planning(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    app_sessions: Any,
    linear: FakeLinear,
    redis: Redis,
) -> None:
    run = await _ready(engine, app_sessions, linear)
    await _to_approval(engine, ctx, run)

    await run_job(ctx, run, resume=await approval(engine, run, approved=True))

    assert (await run_row(engine, run)).status == "succeeded"
    assert await idea_stage(engine, run) == "exported"
    jobs = await export_jobs(engine, run)
    assert [j["status"] for j in jobs] == ["succeeded"]
    assert jobs[0]["summary"]["plan_version"] == 1
    assert jobs[0]["summary"]["issues"]["total"] == 3
    assert await saved_team(engine, run) == "team-2"
    values = await checkpoint_values(run)
    assert values["pending_approval"] is None
    assert values["export_state"] == "approved"
    assert await plan_status(engine, run) == "draft"
    finished = [e for e in await events_of(redis, run) if e.type is RunEventType.EXPORT_FINISHED]
    assert [e.data["created"] for e in finished] == [7]
    assert linear.write_calls[:4] == [
        "save_project",
        "save_milestone",
        "save_milestone",
        "save_milestone",
    ]


async def test_rejecting_records_the_decision_and_leaves_everything_as_it_was(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _ready(engine, app_sessions, linear)
    await _to_approval(engine, ctx, run)

    await run_job(ctx, run, resume=await approval(engine, run, approved=False))

    assert (await run_row(engine, run)).status == "succeeded"
    assert await idea_stage(engine, run) == "planning"
    assert [j["status"] for j in await export_jobs(engine, run)] == ["declined"]
    values = await checkpoint_values(run)
    assert values["pending_approval"] is None
    assert values["export_state"] == "declined"
    assert await plan_status(engine, run) == "draft"
    assert linear.write_calls == []


async def test_the_chosen_team_is_not_saved_until_the_export_is_answered(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _ready(engine, app_sessions, linear)

    await _to_approval(engine, ctx, run)

    assert await saved_team(engine, run) is None
    assert linear.write_calls == []


# ------------------------------------------------------------------ connection
async def test_an_expired_connection_fails_the_run(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await export_run(engine, app_sessions)
    await connect_workspace(engine, app_sessions, run.workspace_id, linear, status="expired")

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "mcp.expired"


async def test_a_workspace_that_never_connected_linear_fails_the_run(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await export_run(engine, app_sessions)

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.error is not None and row.error["code"] == "mcp.not_connected"


async def test_a_re_run_after_the_decision_was_recorded_asks_nothing_and_finishes(
    engine: AsyncEngine,
    ctx: dict[str, Any],
    app_sessions: Any,
    linear: FakeLinear,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = await _ready(engine, app_sessions, linear)
    await _to_approval(engine, ctx, run)
    await run_job(ctx, run, resume=await approval(engine, run, approved=True))
    # A crash after the record and the team save, before the checkpoint: the node runs again
    # from its start with the team already saved, so a skipped ``choose_team`` must not shift
    # the stored answers onto the approval.
    node = build_integrator(
        lambda ws: in_workspace(app_sessions, ws), redis, oauth_client(linear), mcp_client(linear)
    )

    def refuse_to_ask(*_: Any, **__: Any) -> Any:
        raise AssertionError("the replay must not interrupt")

    monkeypatch.setattr("metis.agent.specialists.integrator.interrupt", refuse_to_ask)
    monkeypatch.setattr(
        "metis.agent.specialists.integrator.get_stream_writer", lambda: lambda _event: None
    )
    state = initial_state(
        run_id=run.run_id,
        workspace_id=run.workspace_id,
        idea_id=await idea_of(engine, run),
        stage=Stage.PLANNING,
        max_steps=50,
    )

    update = await node(state)

    assert update["export_state"] == "approved"
    assert update["pending_approval"] is None  # the finished export clears the approval
    assert len(await export_jobs(engine, run)) == 1
    assert await saved_team(engine, run) == "team-2"
