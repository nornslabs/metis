"""HTTP contract for the manual rescore and market re-check operations."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.core import jobs
from metis.core.db import set_workspace
from metis.modules import ideas, research
from tests.modules.ideas.idea_helpers import IDEAS_URL, Caller, create, owner

Sessions = async_sessionmaker[AsyncSession]


@pytest.fixture
def queued_runs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def fake_enqueue(job_name: str, *args: Any, **kwargs: Any) -> None:
        calls.append({"job": job_name, **kwargs})

    monkeypatch.setattr(jobs, "enqueue", fake_enqueue)
    return calls


async def _closed_research(
    sessions: Sessions, caller: Caller, idea_id: str
) -> None:
    workspace_id, idea_uuid = UUID(caller.workspace_id), UUID(idea_id)
    async with sessions() as session:
        await set_workspace(session, workspace_id)
        run = await ideas.create_run(session, workspace_id, idea_uuid)
        await ideas.mark_running(session, workspace_id, run.id)
        await ideas.mark_succeeded(session, workspace_id, run.id)
        snapshot = await research.open_snapshot(session, workspace_id, idea_uuid, run.id)
        await research.close_snapshot(session, workspace_id, snapshot.id, "Market checked.")
        await session.commit()


async def test_rescore_requires_closed_research_and_starts_rescore_run(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    app_sessions: Sessions,
    queued_runs: list[dict[str, Any]],
) -> None:
    caller = await owner(client, engine)
    idea = await create(client, caller)
    url = f"{IDEAS_URL}/{idea['id']}/rescore"
    headers = {**caller.headers, "Idempotency-Key": uuid4().hex}

    response = await client.post(url, headers=headers)
    assert response.status_code == 404
    assert response.json()["code"] == "research.not_found"
    assert "Re-check market" in response.json()["detail"]
    assert queued_runs == []

    await _closed_research(app_sessions, caller, idea["id"])
    response = await client.post(url, headers=headers)
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    replay = await client.post(url, headers=headers)
    assert replay.status_code == 202
    assert replay.json() == response.json()
    run_view = await client.get(f"/v1/runs/{run_id}", headers=caller.headers)
    assert run_view.status_code == 200
    assert run_view.json()["kind"] == "rescore"
    async with engine.connect() as conn:
        kind = await conn.scalar(
            text("SELECT kind FROM ideas.workflow_runs WHERE id = :id"), {"id": run_id}
        )
    assert kind == "rescore"
    assert queued_runs == [
        {
            "job": "run_graph",
            "run_id": run_id,
            "workspace_id": caller.workspace_id,
            "job_id": run_id,
        },
        {
            "job": "run_graph",
            "run_id": run_id,
            "workspace_id": caller.workspace_id,
            "job_id": run_id,
        },
    ]


async def test_recheck_market_starts_market_recheck_run(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queued_runs: list[dict[str, Any]],
) -> None:
    caller = await owner(client, engine)
    idea = await create(client, caller)
    response = await client.post(
        f"{IDEAS_URL}/{idea['id']}/recheck-market",
        headers={**caller.headers, "Idempotency-Key": uuid4().hex},
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    async with engine.connect() as conn:
        kind = await conn.scalar(
            text("SELECT kind FROM ideas.workflow_runs WHERE id = :id"), {"id": run_id}
        )
    assert kind == "market_recheck"
    assert queued_runs == [
        {
            "job": "run_graph",
            "run_id": run_id,
            "workspace_id": caller.workspace_id,
            "job_id": run_id,
        }
    ]
