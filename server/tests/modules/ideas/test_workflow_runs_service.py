"""Runs at the service seam: creation, the status table, RLS and the cross-workspace scan.

There is no route yet (SHIP-232), so these call the ideas module's public functions, as the
``run_graph`` job does. Sessions run as ``metis_app`` so RLS applies, like in production.
"""

from __future__ import annotations

from itertools import product
from uuid import UUID, uuid4

import httpx
import pytest
from idea_helpers import Caller, create, owner
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.core.db import set_workspace
from metis.core.errors import IdeaNotFoundError, IllegalRunTransition, RunNotFoundError
from metis.modules import ideas
from metis.modules.ideas import RunStatus
from metis.modules.ideas.helpers.run_transitions import ALLOWED_RUN_TRANSITIONS

R = RunStatus
LEGAL_MOVES = {
    (R.QUEUED, R.RUNNING),
    (R.QUEUED, R.CANCELLED),
    (R.RUNNING, R.AWAITING_USER),
    (R.RUNNING, R.SUCCEEDED),
    (R.RUNNING, R.FAILED),
    (R.RUNNING, R.CANCELLED),
    (R.AWAITING_USER, R.RUNNING),
    (R.AWAITING_USER, R.CANCELLED),
}
QUESTION = {"type": "question", "question": "Who pays?"}


async def _idea(client: httpx.AsyncClient, caller: Caller) -> UUID:
    return UUID((await create(client, caller))["id"])


async def _new_run(
    sessions: async_sessionmaker[AsyncSession],
    caller: Caller,
    idea_id: UUID,
    key: str | None = None,
) -> UUID:
    workspace_id = UUID(caller.workspace_id)
    async with sessions() as session:
        await set_workspace(session, workspace_id)
        run = await ideas.create_run(session, workspace_id, idea_id, idempotency_key=key)
        await session.commit()
    return run.id


async def _force_status(engine: AsyncEngine, run_id: UUID, status: RunStatus) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE ideas.workflow_runs SET status = :s WHERE id = :id"),
            {"s": status.value, "id": run_id},
        )


async def _get(sessions: async_sessionmaker[AsyncSession], caller: Caller, run_id: UUID):  # type: ignore[no-untyped-def]
    workspace_id = UUID(caller.workspace_id)
    async with sessions() as session:
        await set_workspace(session, workspace_id)
        return await ideas.get_run(session, workspace_id, run_id)


async def _move(
    sessions: async_sessionmaker[AsyncSession], caller: Caller, run_id: UUID, target: RunStatus
):  # type: ignore[no-untyped-def]
    workspace_id = UUID(caller.workspace_id)
    async with sessions() as session:
        await set_workspace(session, workspace_id)
        moves = {
            R.RUNNING: lambda: ideas.mark_running(session, workspace_id, run_id),
            R.AWAITING_USER: lambda: ideas.mark_awaiting_user(
                session, workspace_id, run_id, QUESTION
            ),
            R.SUCCEEDED: lambda: ideas.mark_succeeded(session, workspace_id, run_id),
            R.FAILED: lambda: ideas.mark_failed(
                session, workspace_id, run_id, {"code": "run.failed", "message": "boom"}
            ),
            R.CANCELLED: lambda: ideas.mark_cancelled(session, workspace_id, run_id),
        }
        run = await moves[target]()
        await session.commit()
        return run


def test_the_table_allows_exactly_the_agreed_moves() -> None:
    actual = {(src, dst) for src, targets in ALLOWED_RUN_TRANSITIONS.items() for dst in targets}

    assert actual == LEGAL_MOVES
    assert set(ALLOWED_RUN_TRANSITIONS) == set(RunStatus)


async def test_a_new_run_is_queued_on_its_idea(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    ada = await owner(client, engine)
    idea_id = await _idea(client, ada)

    run = await _get(app_sessions, ada, await _new_run(app_sessions, ada, idea_id))

    assert (run.status, run.idea_id, run.kind.value) == (R.QUEUED, idea_id, "pipeline")
    assert (run.started_at, run.finished_at, run.error, run.pending_interrupt) == (
        None,
        None,
        None,
        None,
    )
    assert run.version == 1


async def test_a_run_needs_an_idea_of_its_own_workspace(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    ada = await owner(client, engine, "ada")
    grace = await owner(client, engine, "grace")
    ada_idea = await _idea(client, ada)

    with pytest.raises(IdeaNotFoundError):
        await _new_run(app_sessions, grace, ada_idea)
    with pytest.raises(IdeaNotFoundError):
        await _new_run(app_sessions, ada, uuid4())


async def test_an_idempotency_key_is_unique_per_workspace_only(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    ada = await owner(client, engine, "ada")
    grace = await owner(client, engine, "grace")
    ada_idea, grace_idea = await _idea(client, ada), await _idea(client, grace)
    await _new_run(app_sessions, ada, ada_idea, key="k1")

    await _new_run(app_sessions, grace, grace_idea, key="k1")
    await _new_run(app_sessions, ada, ada_idea)
    await _new_run(app_sessions, ada, ada_idea)
    with pytest.raises(IntegrityError):
        await _new_run(app_sessions, ada, ada_idea, key="k1")


@pytest.mark.parametrize(
    ("source", "target"), sorted(LEGAL_MOVES, key=lambda m: (m[0].value, m[1].value))
)
async def test_a_legal_move_changes_the_status_and_bumps_the_version(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    source: RunStatus,
    target: RunStatus,
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(app_sessions, ada, await _idea(client, ada))
    await _force_status(engine, run_id, source)

    moved = await _move(app_sessions, ada, run_id, target)

    assert moved.status is target
    assert moved.version == 2
    assert (await _get(app_sessions, ada, run_id)).status is target


@pytest.mark.parametrize(
    ("source", "target"),
    sorted(
        # Nothing moves a run back to ``queued`` (no service function); the table test covers it.
        {pair for pair in product(RunStatus, RunStatus) if pair[1] is not R.QUEUED}
        - LEGAL_MOVES
        - {(R.RUNNING, R.RUNNING)},
        key=lambda m: (m[0].value, m[1].value),
    ),
)
async def test_an_illegal_move_raises_and_changes_nothing(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    source: RunStatus,
    target: RunStatus,
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(app_sessions, ada, await _idea(client, ada))
    await _force_status(engine, run_id, source)

    with pytest.raises(IllegalRunTransition) as caught:
        await _move(app_sessions, ada, run_id, target)

    assert (caught.value.status, caught.value.code) == (409, "run.invalid_state")
    assert (await _get(app_sessions, ada, run_id)).status is source


async def test_running_a_run_that_is_already_running_changes_nothing(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(app_sessions, ada, await _idea(client, ada))
    first = await _move(app_sessions, ada, run_id, R.RUNNING)

    again = await _move(app_sessions, ada, run_id, R.RUNNING)

    assert (again.version, again.started_at) == (first.version, first.started_at)


async def test_the_interrupt_is_stored_while_waiting_and_cleared_on_resume(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(app_sessions, ada, await _idea(client, ada))
    started = await _move(app_sessions, ada, run_id, R.RUNNING)

    waiting = await _move(app_sessions, ada, run_id, R.AWAITING_USER)
    resumed = await _move(app_sessions, ada, run_id, R.RUNNING)

    assert waiting.pending_interrupt == QUESTION
    assert resumed.pending_interrupt is None
    assert resumed.started_at == started.started_at


async def test_a_failed_run_keeps_its_error_and_a_finished_run_has_a_finish_time(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    ada = await owner(client, engine)
    run_id = await _new_run(app_sessions, ada, await _idea(client, ada))
    await _move(app_sessions, ada, run_id, R.RUNNING)

    failed = await _move(app_sessions, ada, run_id, R.FAILED)

    assert failed.error == {"code": "run.failed", "message": "boom"}
    assert failed.finished_at is not None


async def test_a_run_is_invisible_to_another_workspace(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    ada = await owner(client, engine, "ada")
    grace = await owner(client, engine, "grace")
    run_id = await _new_run(app_sessions, ada, await _idea(client, ada))

    with pytest.raises(RunNotFoundError):
        await _get(app_sessions, grace, run_id)
    async with app_sessions() as session:  # no workspace set: RLS shows nothing, even for ada's id
        with pytest.raises(RunNotFoundError):
            await ideas.get_run(session, UUID(ada.workspace_id), run_id)


async def test_the_scan_lists_running_runs_of_every_workspace_and_only_those(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    ada = await owner(client, engine, "ada")
    grace = await owner(client, engine, "grace")
    running_a = await _new_run(app_sessions, ada, await _idea(client, ada))
    running_g = await _new_run(app_sessions, grace, await _idea(client, grace))
    await _new_run(app_sessions, ada, await _idea(client, ada))  # queued
    waiting = await _new_run(app_sessions, ada, await _idea(client, ada))
    await _move(app_sessions, ada, running_a, R.RUNNING)
    await _move(app_sessions, grace, running_g, R.RUNNING)
    await _move(app_sessions, ada, waiting, R.RUNNING)
    await _move(app_sessions, ada, waiting, R.AWAITING_USER)

    async with app_sessions() as session:  # no workspace set
        refs = await ideas.list_running_runs(session)

    assert {(ref.run_id, ref.workspace_id) for ref in refs} == {
        (running_a, UUID(ada.workspace_id)),
        (running_g, UUID(grace.workspace_id)),
    }
