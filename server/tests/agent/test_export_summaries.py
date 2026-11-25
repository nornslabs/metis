"""``integrations.service.exports.export_summaries`` (SHIP-255): what the web reads after a reload.

Seam: the service called with a scoped ``metis_app`` session, on jobs written by the same public
functions the Integrator uses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.modules import integrations
from metis.modules.integrations import ExportStatus
from metis.modules.integrations.service import exports
from tests.agent.export_helpers import export_run, owner_of
from tests.agent.planner_helpers import idea_of
from tests.modules.scoring.scoring_helpers import in_workspace


async def _started_job(
    engine: AsyncEngine, sessions: async_sessionmaker[AsyncSession]
) -> tuple[Any, Any]:
    run = await export_run(engine, sessions)
    idea_id = await idea_of(engine, run)
    async with engine.connect() as conn:
        plan_id = await conn.scalar(
            text("SELECT id FROM planning.plans WHERE idea_id = :idea"), {"idea": idea_id}
        )
    owner = await owner_of(engine, run)
    async with in_workspace(sessions, run.workspace_id) as session:
        await integrations.record_export_decision(
            session,
            run.workspace_id,
            idea_id=idea_id,
            plan_id=plan_id,
            run_id=run.run_id,
            approved=True,
            decided_by=owner,
            decided_at=datetime.now(UTC),
            summary={},
        )
        await integrations.mark_export_running(session, run.workspace_id, run.run_id)
    return run, idea_id


async def _summaries(
    sessions: async_sessionmaker[AsyncSession], run: Any, idea_id: Any
) -> list[Any]:
    async with in_workspace(sessions, run.workspace_id) as session:
        listing = await exports.export_summaries(session, run.workspace_id, [idea_id])
    return listing.items


async def test_a_finished_export_is_summarised_with_its_project_url_and_counts(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, idea_id = await _started_job(engine, app_sessions)
    result = {"created": 4, "updated": 1, "links": 2, "failed": [], "project_url": "https://x/p"}
    async with in_workspace(app_sessions, run.workspace_id) as session:
        await integrations.finish_export(
            session, run.workspace_id, run.run_id, ExportStatus.SUCCEEDED, result
        )

    [summary] = await _summaries(app_sessions, run, idea_id)

    assert summary.idea_id == idea_id
    assert summary.status is ExportStatus.SUCCEEDED
    assert (summary.project_url, summary.created, summary.updated, summary.links) == (
        "https://x/p",
        4,
        1,
        2,
    )
    assert summary.failed == [] and summary.finished_at is not None


async def test_a_partial_export_lists_the_items_that_failed(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, idea_id = await _started_job(engine, app_sessions)
    failed = [{"kind": "issue", "local_id": "x", "name": "Build it", "reason": "rate_limited"}]
    result = {
        "created": 2,
        "updated": 0,
        "links": 0,
        "failed": failed,
        "project_url": "https://x/p",
    }
    async with in_workspace(app_sessions, run.workspace_id) as session:
        await integrations.finish_export(
            session, run.workspace_id, run.run_id, ExportStatus.PARTIAL, result
        )

    [summary] = await _summaries(app_sessions, run, idea_id)

    assert summary.status is ExportStatus.PARTIAL
    assert [(f.kind, f.name, f.reason) for f in summary.failed] == [
        ("issue", "Build it", "rate_limited")
    ]


async def test_an_export_that_has_not_finished_is_left_out(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, idea_id = await _started_job(engine, app_sessions)

    assert await _summaries(app_sessions, run, idea_id) == []
