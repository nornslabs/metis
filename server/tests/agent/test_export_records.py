"""The export records the Integrator keeps (SHIP-252): export jobs, external refs and the
workspace's Linear team.

Seam: the public functions of ``integrations`` and ``identity`` called as the node calls them
(a scoped ``metis_app`` session), plus the database's own constraints on ``export_jobs``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.core.errors import ConflictError
from metis.modules import identity, integrations
from metis.modules.integrations import ExportStatus, IntegrationProvider, LocalKind
from tests.agent.export_helpers import (
    add_refs,
    export_jobs,
    export_run,
    external_refs,
    local_ids,
    outbox_count,
    owner_of,
    saved_team,
)
from tests.agent.planner_helpers import idea_of
from tests.modules.scoring.scoring_helpers import in_workspace


async def _record(
    engine: AsyncEngine, sessions: async_sessionmaker[AsyncSession], *, approved: bool
) -> tuple[Any, Any]:
    run = await export_run(engine, sessions)
    idea_id = await idea_of(engine, run)
    async with engine.connect() as conn:
        plan_id = await conn.scalar(
            text("SELECT id FROM planning.plans WHERE idea_id = :idea"), {"idea": idea_id}
        )
    owner = await owner_of(engine, run)
    async with in_workspace(sessions, run.workspace_id) as session:
        job = await integrations.record_export_decision(
            session,
            run.workspace_id,
            idea_id=idea_id,
            plan_id=plan_id,
            run_id=run.run_id,
            approved=approved,
            decided_by=owner,
            decided_at=datetime.now(UTC),
            summary={"issues": {"total": 3}},
        )
    return run, job


async def test_an_approval_is_recorded_with_who_decided(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, job = await _record(engine, app_sessions, approved=True)

    assert job.status is ExportStatus.APPROVED
    assert job.decided_by == await owner_of(engine, run)
    assert [j["status"] for j in await export_jobs(engine, run)] == ["approved"]


async def test_a_rejection_is_recorded_as_declined(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, job = await _record(engine, app_sessions, approved=False)

    assert job.status is ExportStatus.DECLINED
    assert [j["status"] for j in await export_jobs(engine, run)] == ["declined"]


async def test_recording_the_same_runs_decision_twice_keeps_the_first(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, first = await _record(engine, app_sessions, approved=True)
    idea_id = await idea_of(engine, run)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        second = await integrations.record_export_decision(
            session,
            run.workspace_id,
            idea_id=idea_id,
            plan_id=first.plan_id,
            run_id=run.run_id,
            approved=False,
            decided_by=uuid4(),
            decided_at=datetime.now(UTC),
            summary={},
        )

    assert second.id == first.id and second.status is ExportStatus.APPROVED
    assert len(await export_jobs(engine, run)) == 1


async def test_the_database_refuses_an_unknown_export_status(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, _ = await _record(engine, app_sessions, approved=True)

    with pytest.raises(IntegrityError, match="ck_export_jobs_status"):
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE integrations.export_jobs SET status = 'exploded' WHERE run_id = :r"),
                {"r": run.run_id},
            )


async def test_external_refs_come_back_by_local_id_for_one_kind_only(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await export_run(engine, app_sessions)
    tasks = await local_ids(engine, run, "tasks")
    phases = await local_ids(engine, run, "phases")
    await add_refs(engine, run, "task", tasks[:2])
    await add_refs(engine, run, "phase", phases[:1])

    async with in_workspace(app_sessions, run.workspace_id) as session:
        found = await integrations.list_external_refs(
            session,
            run.workspace_id,
            integrations.IntegrationProvider.LINEAR,
            LocalKind.TASK,
            tasks,
        )

    assert set(found) == set(tasks[:2])
    assert {ref.external_id for ref in found.values()} == {"ext"}


async def test_another_workspace_sees_none_of_the_refs(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await export_run(engine, app_sessions)
    tasks = await local_ids(engine, run, "tasks")
    await add_refs(engine, run, "task", tasks)
    other = await export_run(engine, app_sessions, sub="bob")

    async with in_workspace(app_sessions, other.workspace_id) as session:
        found = await integrations.list_external_refs(
            session,
            other.workspace_id,
            integrations.IntegrationProvider.LINEAR,
            LocalKind.TASK,
            tasks,
        )

    assert found == {}


async def test_the_linear_team_is_saved_with_default_limits_when_no_settings_exist(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await export_run(engine, app_sessions)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        await identity.set_linear_team(session, run.workspace_id, "team-2")
    async with in_workspace(app_sessions, run.workspace_id) as session:
        overview = await identity.get_settings_overview(session, run.workspace_id)

    assert await saved_team(engine, run) == "team-2"
    assert overview.settings.linear_team_id == "team-2"
    assert (overview.settings.max_steps, str(overview.settings.run_budget_usd)) == (50, "2.00")


async def test_changing_the_linear_team_keeps_the_settings_version(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await export_run(engine, app_sessions)
    async with in_workspace(app_sessions, run.workspace_id) as session:
        await identity.set_linear_team(session, run.workspace_id, "team-1")
        before = (await identity.get_settings_overview(session, run.workspace_id)).settings

        await identity.set_linear_team(session, run.workspace_id, "team-2")
        after = (await identity.get_settings_overview(session, run.workspace_id)).settings

    assert (before.linear_team_id, after.linear_team_id) == ("team-1", "team-2")
    assert after.version == before.version


async def test_a_workspace_never_sees_another_workspaces_linear_team(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run = await export_run(engine, app_sessions)
    other = await export_run(engine, app_sessions, sub="bob")
    async with in_workspace(app_sessions, run.workspace_id) as session:
        await identity.set_linear_team(session, run.workspace_id, "team-1")

    async with in_workspace(app_sessions, other.workspace_id) as session:
        overview = await identity.get_settings_overview(session, other.workspace_id)

    assert overview.settings.linear_team_id is None


async def test_saving_a_ref_twice_updates_the_one_row(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, _ = await _record(engine, app_sessions, approved=True)
    idea_id = await idea_of(engine, run)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        for external_id in ("project-1", "project-2"):
            await integrations.save_external_ref(
                session,
                run.workspace_id,
                IntegrationProvider.LINEAR,
                LocalKind.IDEA,
                idea_id,
                external_id,
                f"https://linear.app/{external_id}",
            )

    assert await external_refs(engine, run) == {("idea", idea_id): "project-2"}


async def test_a_saved_ref_is_found_by_its_workspace_only(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, _ = await _record(engine, app_sessions, approved=True)
    other = await export_run(engine, app_sessions, sub="bob")
    idea_id = await idea_of(engine, run)
    async with in_workspace(app_sessions, run.workspace_id) as session:
        await integrations.save_external_ref(
            session,
            run.workspace_id,
            IntegrationProvider.LINEAR,
            LocalKind.IDEA,
            idea_id,
            "project-1",
            None,
        )

    async with in_workspace(app_sessions, other.workspace_id) as session:
        found = await integrations.list_external_refs(
            session, other.workspace_id, IntegrationProvider.LINEAR, LocalKind.IDEA, [idea_id]
        )

    assert found == {}


async def test_marking_an_approved_export_running_twice_changes_nothing_more(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, _ = await _record(engine, app_sessions, approved=True)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        first = await integrations.mark_export_running(session, run.workspace_id, run.run_id)
        second = await integrations.mark_export_running(session, run.workspace_id, run.run_id)

    assert first.id == second.id and second.status is ExportStatus.RUNNING
    assert [j["status"] for j in await export_jobs(engine, run)] == ["running"]


async def test_a_declined_export_cannot_be_marked_running(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, _ = await _record(engine, app_sessions, approved=False)

    with pytest.raises(ConflictError):
        async with in_workspace(app_sessions, run.workspace_id) as session:
            await integrations.mark_export_running(session, run.workspace_id, run.run_id)

    assert [j["status"] for j in await export_jobs(engine, run)] == ["declined"]


async def test_finishing_a_running_export_stores_the_result_and_writes_one_event(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, _ = await _record(engine, app_sessions, approved=True)
    result = {"created": 4, "updated": 1, "links": 2, "failed": [], "project_url": "https://x/p"}
    async with in_workspace(app_sessions, run.workspace_id) as session:
        await integrations.mark_export_running(session, run.workspace_id, run.run_id)
        first = await integrations.finish_export(
            session, run.workspace_id, run.run_id, ExportStatus.SUCCEEDED, result
        )
        second = await integrations.finish_export(
            session, run.workspace_id, run.run_id, ExportStatus.FAILED, {"created": 0}
        )

    assert first.status is ExportStatus.SUCCEEDED and first.finished_at is not None
    assert second.status is ExportStatus.SUCCEEDED  # a job that is not running is left alone
    [job] = await export_jobs(engine, run)
    assert job["status"] == "succeeded"
    assert job["summary"]["result"] == result
    assert "issues" in job["summary"]  # the preview the user saw is kept
    assert await outbox_count(engine, run, "ExportFinished") == 1


async def test_a_partial_or_failed_finish_writes_no_event(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, _ = await _record(engine, app_sessions, approved=True)
    async with in_workspace(app_sessions, run.workspace_id) as session:
        await integrations.mark_export_running(session, run.workspace_id, run.run_id)
        await integrations.finish_export(
            session, run.workspace_id, run.run_id, ExportStatus.PARTIAL, {"created": 1}
        )

    assert [j["status"] for j in await export_jobs(engine, run)] == ["partial"]
    assert await outbox_count(engine, run, "ExportFinished") == 0


async def test_an_export_cannot_be_finished_as_approved_or_declined(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, _ = await _record(engine, app_sessions, approved=True)

    with pytest.raises(ValueError):
        async with in_workspace(app_sessions, run.workspace_id) as session:
            await integrations.finish_export(
                session, run.workspace_id, run.run_id, ExportStatus.APPROVED, {}
            )


async def test_finishing_a_job_before_it_runs_changes_nothing(
    engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    run, _ = await _record(engine, app_sessions, approved=True)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        job = await integrations.finish_export(
            session, run.workspace_id, run.run_id, ExportStatus.SUCCEEDED, {}
        )

    assert job.status is ExportStatus.APPROVED
    assert await outbox_count(engine, run, "ExportFinished") == 0
