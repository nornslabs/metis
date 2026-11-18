"""Research routes: ``GET /v1/ideas/{id}/research`` and ``GET /v1/research/snapshots/{id}``.

Research is written through the module's service (the Researcher's path) and read over HTTP.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.helpers.ids import uuid7
from metis.modules import research
from tests.modules.ideas.idea_helpers import IDEAS_URL, Caller, create, member_of, owner
from tests.modules.research.research_helpers import competitor, in_workspace, item, vector

Sessions = async_sessionmaker[AsyncSession]


async def _research(
    engine: AsyncEngine, sessions: Sessions, caller: Caller, idea_id: str, close: bool = True
) -> UUID:
    """A snapshot of the idea with one item and one linked competitor; returns its id."""
    workspace_id, idea = UUID(caller.workspace_id), UUID(idea_id)
    run_id = uuid7()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ideas.workflow_runs (id, workspace_id, idea_id) "
                "VALUES (:id, :ws, :idea)"
            ),
            {"id": run_id, "ws": workspace_id, "idea": idea},
        )
    async with in_workspace(sessions, workspace_id) as session:
        snapshot = await research.open_snapshot(session, workspace_id, idea, run_id)
        await research.add_item(session, workspace_id, snapshot.id, item())
        acme = await research.upsert_competitor(
            session, workspace_id, competitor(embedding=vector(1.0), pricing="$9")
        )
        await research.link_competitor(session, workspace_id, snapshot.id, acme.id, 0.6)
        if close:
            await research.close_snapshot(session, workspace_id, snapshot.id, "Crowded market.")
    return snapshot.id


async def _get(client: httpx.AsyncClient, caller: Caller, url: str) -> httpx.Response:
    return await client.get(url, headers=caller.headers)


def _code(response: httpx.Response) -> Any:
    return response.json()["code"]


async def test_the_latest_research_of_an_idea_is_readable_by_any_member(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    bob = await member_of(client, engine, ada)
    idea = await create(client, ada)
    snapshot_id = await _research(engine, app_sessions, ada, idea["id"])

    response = await _get(client, bob, f"{IDEAS_URL}/{idea['id']}/research")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["id"], body["idea_id"], body["summary"]) == (
        str(snapshot_id),
        idea["id"],
        "Crowded market.",
    )
    assert body["closed_at"] is not None
    [fact] = body["items"]
    assert fact["kind"] == "market_fact"
    assert fact["url"] == "https://example.com/report"
    assert fact["confidence"] == 0.8
    [acme] = body["competitors"]
    assert (acme["name"], acme["domain"], acme["pricing"], acme["overlap"]) == (
        "Acme CRM",
        "acme.com",
        "$9",
        0.6,
    )
    for hidden in ("workspace_id", "embedding"):
        assert hidden not in body
        assert hidden not in acme


async def test_an_idea_without_closed_research_is_research_not_found(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    await _research(engine, app_sessions, ada, idea["id"], close=False)

    response = await _get(client, ada, f"{IDEAS_URL}/{idea['id']}/research")

    assert response.status_code == 404
    assert _code(response) == "research.not_found"


async def test_research_of_unknown_archived_or_foreign_ideas_is_idea_not_found(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    grace = await owner(client, engine, "grace")
    idea = await create(client, ada)
    await _research(engine, app_sessions, ada, idea["id"])

    foreign = await _get(client, grace, f"{IDEAS_URL}/{idea['id']}/research")
    unknown = await _get(client, ada, f"{IDEAS_URL}/{uuid7()}/research")
    await client.delete(f"{IDEAS_URL}/{idea['id']}", headers=ada.headers)
    archived = await _get(client, ada, f"{IDEAS_URL}/{idea['id']}/research")

    for response in (foreign, unknown, archived):
        assert response.status_code == 404
        assert _code(response) == "idea.not_found"


async def test_a_snapshot_is_readable_by_id_even_while_open(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    snapshot_id = await _research(engine, app_sessions, ada, idea["id"], close=False)

    response = await _get(client, ada, f"/v1/research/snapshots/{snapshot_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["summary"], body["closed_at"]) == (None, None)
    assert len(body["items"]) == 1
    assert len(body["competitors"]) == 1


async def test_unknown_or_foreign_snapshots_are_not_found(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    grace = await owner(client, engine, "grace")
    idea = await create(client, ada)
    snapshot_id = await _research(engine, app_sessions, ada, idea["id"])

    for response in (
        await _get(client, grace, f"/v1/research/snapshots/{snapshot_id}"),
        await _get(client, ada, f"/v1/research/snapshots/{uuid7()}"),
    ):
        assert response.status_code == 404
        assert _code(response) == "research.snapshot_not_found"
