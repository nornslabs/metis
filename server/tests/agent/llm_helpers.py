"""Setup helpers for the LLM gateway tests: a workspace with a saved LLM key, and usage rows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from metis.helpers.ids import uuid7
from metis.modules import auth, identity
from metis.modules.identity import MemberRole, Membership, ProviderKind
from metis.modules.identity.service.provider_keys import set_key
from tests.helpers.auth import create_user

LLM_KEY = "sk-test-secret-key-0123456789"
LLM_BASE_URL = "https://llm.example.com/v1"
LLM_MODEL = "test-model"


Responder = Callable[[httpx.Request], httpx.Response]

DEFAULT_USAGE = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


def chat_completion(
    content: str = "hello", usage: dict[str, int] | None = DEFAULT_USAGE
) -> httpx.Response:
    """A minimal OpenAI ``chat.completion`` response."""
    body: dict[str, object] = {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
    if usage is not None:
        body["usage"] = usage
    return httpx.Response(200, json=body)


@dataclass
class FakeLLMServer:
    """An OpenAI-compatible endpoint behind ``httpx.MockTransport``; records every request."""

    requests: list[httpx.Request] = field(default_factory=list)
    responder: Responder = field(default=lambda _request: chat_completion())

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responder(request)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))


@dataclass(frozen=True)
class UsageRow:
    run_id: UUID
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal | None


async def workspace_with_key(
    engine: AsyncEngine, sub: str = "ada", key: str = LLM_KEY, model: str = LLM_MODEL
) -> UUID:
    """A user's personal workspace with an LLM key saved; returns the workspace id."""
    user_id = await create_user(engine, sub, f"{sub}@example.com", sub.title())
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = await auth.get_user(session, user_id)
        assert user is not None
        workspace = await identity.ensure_personal_workspace(session, user)
        owner = Membership(workspace=workspace, role=MemberRole.OWNER)
        await set_key(session, owner, ProviderKind.LLM, key, LLM_BASE_URL, model)
        await session.commit()
    return workspace.id


async def workspace_without_key(engine: AsyncEngine, sub: str = "grace") -> UUID:
    user_id = await create_user(engine, sub, f"{sub}@example.com", sub.title())
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = await auth.get_user(session, user_id)
        assert user is not None
        workspace = await identity.ensure_personal_workspace(session, user)
        await session.commit()
    return workspace.id


async def usage_rows(engine: AsyncEngine, workspace_id: UUID) -> list[UsageRow]:
    """The workspace's usage rows, read as the DB owner, oldest first."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT run_id, model, input_tokens, output_tokens, cost_usd "
                "FROM ideas.llm_usage WHERE workspace_id = :ws ORDER BY created_at, id"
            ),
            {"ws": workspace_id},
        )
        return [UsageRow(*row) for row in result.all()]


async def make_run(engine: AsyncEngine, workspace_id: UUID, stage: str = "intake") -> UUID:
    """A queued run (and its idea, at ``stage``) in the workspace, inserted as the DB owner.

    ``ideas.llm_usage.run_id`` references ``ideas.workflow_runs``, so a usage row needs a real run.
    """
    idea_id, run_id = uuid7(), uuid7()
    async with engine.begin() as conn:
        creator = await conn.scalar(
            text("SELECT created_by FROM identity.workspaces WHERE id = :ws"), {"ws": workspace_id}
        )
        await conn.execute(
            text(
                "INSERT INTO ideas.ideas (id, workspace_id, created_by, title, raw_text, stage) "
                "VALUES (:id, :ws, :by, 'Pocket CRM', 'A tiny CRM for freelancers.', :stage)"
            ),
            {"id": idea_id, "ws": workspace_id, "by": creator, "stage": stage},
        )
        await conn.execute(
            text(
                "INSERT INTO ideas.workflow_runs (id, workspace_id, idea_id) "
                "VALUES (:id, :ws, :idea)"
            ),
            {"id": run_id, "ws": workspace_id, "idea": idea_id},
        )
    return run_id
