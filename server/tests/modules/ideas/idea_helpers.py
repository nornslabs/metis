"""Helpers for the ideas HTTP-seam tests: a signed-in owner, a second member, idea payloads.

Sign-in helpers live in ``tests/helpers/auth.py``; fixtures in ``tests/modules/conftest.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from metis.modules import auth as auth_module
from metis.modules import identity
from metis.modules.identity import MemberRole, Membership, ProviderKind
from metis.modules.identity.service.provider_keys import set_key
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


async def owner(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    sub: str = "owner",
    *,
    llm_key_tested: bool | None = True,
) -> Caller:
    """A new user acting in their own personal workspace (so, its owner).

    The workspace has an LLM key saved, since a run cannot start without one that passed its
    test. ``llm_key_tested`` sets that result (``None``: never tested, ``False``: failed);
    ``delete_llm_key`` removes the key again.
    """
    token = await sign_in(engine, sub, f"{sub}@example.com", sub.title())
    body = await me(client, token)
    caller = Caller(token, body["user"]["id"], body["current_workspace"]["workspace"]["id"])
    await save_llm_key(engine, caller, tested=llm_key_tested)
    return caller


async def save_llm_key(engine: AsyncEngine, caller: Caller, *, tested: bool | None) -> None:
    """Save an LLM key in the caller's workspace and set its last test result."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = await auth_module.get_user(session, UUID(caller.user_id))
        assert user is not None
        workspace = await identity.ensure_personal_workspace(session, user)
        membership = Membership(workspace=workspace, role=MemberRole.OWNER)
        await set_key(
            session, membership, ProviderKind.LLM, "sk-test-key", "https://llm.example.com/v1", "m"
        )
        await session.commit()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE identity.provider_keys SET last_test_ok = :ok, "
                "last_tested_at = CASE WHEN CAST(:ok AS boolean) IS NULL THEN NULL ELSE now() END "
                "WHERE workspace_id = :ws AND kind = 'llm'"
            ),
            {"ok": tested, "ws": caller.workspace_id},
        )


async def delete_llm_key(engine: AsyncEngine, caller: Caller) -> None:
    """Remove the LLM key a test caller starts with."""
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM identity.provider_keys WHERE workspace_id = :ws AND kind = 'llm'"),
            {"ws": caller.workspace_id},
        )


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
