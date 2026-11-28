"""The export's HLD document and Design lines (SHIP-461).

Seam: the ``run_graph`` job with the real Integrator node on real Postgres, Redis and the
checkpointer, with Linear faked in-process (see ``test_integrator_issues.py``). Tests check what
Linear holds (the document, the issue descriptions), what Metis stored (refs) and what the user
is shown (the approval preview), not call order.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.modules import planning
from tests.agent.export_helpers import (
    TOOLS,
    approval,
    export_ctx,
    export_run,
    external_refs,
    next_run,
    reopen_idea,
)
from tests.agent.linear_helpers import connect_workspace
from tests.agent.planner_helpers import idea_of
from tests.agent.run_job_helpers import QueuedRun, run_job, run_row
from tests.helpers.fake_linear import FakeLinear

HLD_MD = (
    "## Overview\n\nA lead tracker.\n\n"
    "## MVP components\n\n### Leads API\n\n**Purpose:** Store leads.\n\n"
    "### Web app\n\n**Purpose:** Show leads.\n\n"
    "## How the components connect\n\nThe web app calls the API."
)
DOCUMENT_URL = "https://linear.app/document/document-1"


def _plan(*, components: bool = True) -> planning.PlanInput:
    phases = tuple(
        planning.PhaseInput(name=name, goal=f"Do {name}.", exit_criteria=f"{name} done.")
        for name in ("Foundations", "Core")
    )
    names = ("Leads API", "Web app") if components else (None, None)
    tasks = (
        planning.TaskInput(
            key="a",
            phase=0,
            title="Task a",
            estimate=3,
            description="## Goal\n\nBuild a.",
            component=names[0],
        ),
        planning.TaskInput(
            key="b",
            phase=1,
            title="Task b",
            estimate=2,
            description="## Goal\n\nBuild b.",
            component=names[1],
        ),
    )
    return planning.PlanInput(phases=phases, tasks=tasks)


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


async def _to_approval(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    ctx: dict[str, Any],
    linear: FakeLinear,
    *,
    hld_md: str | None = HLD_MD,
    components: bool = True,
) -> QueuedRun:
    run = await export_run(engine, sessions, plan_input=_plan(components=components), hld_md=hld_md)
    await connect_workspace(engine, sessions, run.workspace_id, linear)
    await run_job(ctx, run)
    await run_job(ctx, run, resume={"team_id": "team-2"})
    return run


async def _export(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    ctx: dict[str, Any],
    linear: FakeLinear,
    **kwargs: Any,
) -> QueuedRun:
    run = await _to_approval(engine, sessions, ctx, linear, **kwargs)
    await run_job(ctx, run, resume=await approval(engine, run, approved=True))
    return run


def _description(linear: FakeLinear, title: str) -> str:
    [issue] = [i for i in linear.issues.values() if i["title"] == title]
    return str(issue["description"])


async def test_a_software_export_saves_one_document_on_the_project(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _export(engine, app_sessions, ctx, linear)

    [document] = linear.documents.values()
    assert (await run_row(engine, run)).status == "succeeded"
    assert document["project"] == "project-1"
    assert document["content"] == HLD_MD
    assert document["title"].endswith(" HLD")
    project_name = next(iter(linear.projects.values()))["name"]
    assert document["title"] == f"{project_name} HLD"
    refs = await external_refs(engine, run)
    assert refs[("hld", await idea_of(engine, run))] == "document-1"


async def test_every_issue_links_the_document_and_names_its_component(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    await _export(engine, app_sessions, ctx, linear)

    assert f"HLD: {DOCUMENT_URL} · Component: Leads API" in _description(linear, "Task a")
    assert f"HLD: {DOCUMENT_URL} · Component: Web app" in _description(linear, "Task b")
    assert _description(linear, "Task a").rstrip().rsplit("\n", 2)[-2:][0].startswith("---")


async def test_the_design_line_sits_between_the_brief_and_the_footer(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    await _export(engine, app_sessions, ctx, linear)

    description = _description(linear, "Task a")
    assert description.index("Build a.") < description.index("HLD:") < description.index("---")


async def test_a_task_without_a_component_gets_only_the_link(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    await _export(engine, app_sessions, ctx, linear, components=False)

    description = _description(linear, "Task a")
    assert f"HLD: {DOCUMENT_URL}" in description
    assert "Component:" not in description


async def test_a_non_software_export_has_no_document_and_no_design_line(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _export(engine, app_sessions, ctx, linear, hld_md=None, components=False)

    assert (await run_row(engine, run)).status == "succeeded"
    assert linear.documents == {}
    assert "save_document" not in linear.write_calls
    assert all("HLD:" not in i["description"] for i in linear.issues.values())
    assert all(kind != "hld" for kind, _ in await external_refs(engine, run))


async def test_exporting_again_updates_the_same_document(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _export(engine, app_sessions, ctx, linear)
    await reopen_idea(engine, run)
    again = await next_run(engine, run)

    await run_job(ctx, again)
    await run_job(ctx, again, resume=await approval(engine, again, approved=True))

    assert (await run_row(engine, again)).status == "succeeded"
    assert list(linear.documents) == ["document-1"]
    updates = [a for n, a in linear.tool_calls if n == "save_document" and a["id"]]
    assert [a["id"] for a in updates] == ["document-1"]


async def test_the_preview_lists_the_document_and_each_issues_component(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _to_approval(engine, app_sessions, ctx, linear)

    preview = (await run_row(engine, run)).pending_interrupt["preview"]  # type: ignore[index]
    assert preview["hld"]["action"] == "create"
    assert preview["hld"]["title"] == f"{preview['project']['name']} HLD"
    assert [i["component"] for i in preview["issues"]["items"]] == ["Leads API", "Web app"]


async def test_the_preview_of_a_non_software_idea_has_no_hld(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _to_approval(engine, app_sessions, ctx, linear, hld_md=None, components=False)

    preview = (await run_row(engine, run)).pending_interrupt["preview"]  # type: ignore[index]
    assert preview["hld"] is None
    assert {i["component"] for i in preview["issues"]["items"]} == {None}


async def test_declining_the_preview_writes_nothing(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    run = await _to_approval(engine, app_sessions, ctx, linear)

    await run_job(ctx, run, resume=await approval(engine, run, approved=False))

    assert linear.write_calls == []
    assert linear.documents == {}
    assert await external_refs(engine, run) == {}


async def test_a_failed_document_write_stops_the_export_before_any_issue(
    engine: AsyncEngine, ctx: dict[str, Any], app_sessions: Any, linear: FakeLinear
) -> None:
    linear.fail_document_save = True

    run = await _export(engine, app_sessions, ctx, linear)

    assert (await run_row(engine, run)).status == "failed"
    assert linear.issues == {}
    assert linear.documents == {}
