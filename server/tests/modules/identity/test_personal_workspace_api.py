"""Lazy personal workspace: made on the first ``/me`` or workspace-scoped call.

Seam: HTTP requests against the real app (request session as ``metis_app``),
plus a read of ``identity.workspaces`` as the DB owner to count what exists.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from api_helpers import me
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.helpers.auth import auth, sign_in


async def _personal_workspaces(engine: AsyncEngine) -> list[Any]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT id FROM identity.workspaces WHERE is_personal"))
        return [str(workspace_id) for (workspace_id,) in rows]


async def test_a_signed_in_user_has_no_personal_workspace_until_their_first_me(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    token = await sign_in(engine)
    assert await _personal_workspaces(engine) == []

    body = await me(client, token)

    assert await _personal_workspaces(engine) == [body["current_workspace"]["workspace"]["id"]]
    assert body["current_workspace"]["workspace"]["is_personal"] is True
    assert body["current_workspace"]["role"] == "owner"
    assert [m["workspace"]["id"] for m in body["workspaces"]] == await _personal_workspaces(engine)


async def test_first_workspace_scoped_call_creates_the_personal_workspace(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    token = await sign_in(engine)

    response = await client.get("/v1/settings", headers=auth(token))

    assert response.status_code == 200, response.text
    assert len(await _personal_workspaces(engine)) == 1


async def test_first_me_with_a_workspace_header_still_creates_the_personal_workspace(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    token = await sign_in(engine)
    team = await client.post("/v1/workspaces", json={"name": "Team"}, headers=auth(token))
    assert team.status_code == 201, team.text
    assert await _personal_workspaces(engine) == []

    body = await me(client, token, team.json()["workspace"]["id"])

    assert body["current_workspace"]["workspace"]["name"] == "Team"
    assert len(await _personal_workspaces(engine)) == 1
    assert [m["workspace"]["name"] for m in body["workspaces"]] == ["Team", "Personal"]


async def test_calls_that_are_not_workspace_scoped_do_not_create_it(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    token = await sign_in(engine)

    listed = await client.get("/v1/workspaces", headers=auth(token))

    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == []
    assert await _personal_workspaces(engine) == []


async def test_concurrent_first_calls_create_exactly_one_personal_workspace(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    token = await sign_in(engine)

    responses = await asyncio.gather(
        client.get("/v1/me", headers=auth(token)),
        client.get("/v1/settings", headers=auth(token)),
        client.get("/v1/me", headers=auth(token)),
    )

    assert [r.status_code for r in responses] == [200, 200, 200]
    assert len(await _personal_workspaces(engine)) == 1


async def test_first_me_with_a_header_racing_one_without_creates_one_personal_workspace(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    token = await sign_in(engine)
    team = await client.post("/v1/workspaces", json={"name": "Team"}, headers=auth(token))
    assert team.status_code == 201, team.text

    with_header, without_header = await asyncio.gather(
        client.get("/v1/me", headers=auth(token, team.json()["workspace"]["id"])),
        client.get("/v1/me", headers=auth(token)),
    )

    assert [with_header.status_code, without_header.status_code] == [200, 200]
    personal = await _personal_workspaces(engine)
    assert len(personal) == 1
    assert without_header.json()["current_workspace"]["workspace"]["id"] == personal[0]
    assert with_header.json()["current_workspace"]["workspace"]["name"] == "Team"
