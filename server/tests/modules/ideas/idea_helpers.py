"""Helpers for the ideas HTTP-seam tests: a signed-in owner, a second member, idea payloads.

Sign-in helpers live in ``tests/helpers/auth.py``; fixtures in ``tests/modules/conftest.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.helpers.auth import auth, sign_in
from tests.modules.identity.api_helpers import add_member_directly, me

IDEAS_URL = "/v1/ideas"


@dataclass(frozen=True)
class Caller:
    """A signed-in user acting in one workspace."""

    token: str
    user_id: str
    workspace_id: str

    @property
    def headers(self) -> dict[str, str]:
        return auth(self.token, self.workspace_id)


def idea_body(title: str = "Pocket CRM", raw_text: str = "A tiny CRM for freelancers.") -> Any:
    return {"title": title, "raw_text": raw_text}


async def owner(client: httpx.AsyncClient, engine: AsyncEngine, sub: str = "owner") -> Caller:
    """A new user acting in their own personal workspace (so, its owner)."""
    token = await sign_in(engine, sub, f"{sub}@example.com", sub.title())
    body = await me(client, token)
    return Caller(token, body["user"]["id"], body["current_workspace"]["workspace"]["id"])


async def member_of(
    client: httpx.AsyncClient, engine: AsyncEngine, workspace: Caller, sub: str = "member"
) -> Caller:
    """A new user added to ``workspace`` as a plain member."""
    token = await sign_in(engine, sub, f"{sub}@example.com", sub.title())
    user_id = (await client.get("/v1/auth/me", headers=auth(token))).json()["id"]
    await add_member_directly(engine, workspace.workspace_id, user_id)
    return Caller(token, user_id, workspace.workspace_id)


async def create(client: httpx.AsyncClient, caller: Caller, **body: Any) -> Any:
    """Create an idea through the API and return its JSON."""
    response = await client.post(IDEAS_URL, json=idea_body(**body), headers=caller.headers)
    assert response.status_code == 201, response.text
    return response.json()
