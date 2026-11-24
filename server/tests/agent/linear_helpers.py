"""Setup for the Linear tool tests: a workspace with a stored Linear connection, and the HTTP
client factories that route the token refresh and the MCP sessions to ``FakeLinear``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.adapters.mcp.linear import SERVER_URL
from metis.agent.tools.mcp import McpRunContext
from metis.modules.integrations import IntegrationProvider
from metis.modules.integrations.helpers.sealing import StoredTokens, seal_tokens
from metis.modules.integrations.repo import connections
from tests.helpers.fake_linear import AUTH_ISSUER, CLIENT_ID, FakeLinear
from tests.modules.scoring.scoring_helpers import in_workspace

if TYPE_CHECKING:
    from uuid import UUID


def oauth_client(linear: FakeLinear) -> Any:
    """The factory a token refresh uses."""
    transport = linear.transport()
    return lambda headers: httpx.AsyncClient(transport=transport, headers=dict(headers))


def mcp_client(linear: FakeLinear) -> Any:
    """The factory under Linear's MCP sessions."""
    transport = linear.transport()

    def make(
        headers: dict[str, str] | None = None, timeout: Any = None, auth: Any = None
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, headers=headers or {})

    return make


async def connect_workspace(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    workspace_id: UUID,
    linear: FakeLinear,
    *,
    status: str = "connected",
    refresh_token: bool = True,
) -> None:
    """Store a Linear connection whose tokens the fake accepts."""
    access, refresh = linear.issue_tokens()
    tokens = StoredTokens(
        access_token=SecretStr(access),
        refresh_token=SecretStr(refresh) if refresh_token else None,
        client_id=CLIENT_ID,
        token_endpoint=f"{AUTH_ISSUER}/token",
    )
    async with engine.connect() as conn:
        user_id = await conn.scalar(
            text("SELECT user_id FROM identity.members WHERE workspace_id = :ws LIMIT 1"),
            {"ws": workspace_id},
        )
    async with in_workspace(sessions, workspace_id) as session:
        await connections.upsert_connected(
            session,
            workspace_id,
            IntegrationProvider.LINEAR,
            server_url=SERVER_URL,
            sealed_tokens=seal_tokens(tokens, workspace_id),
            scopes=["read", "write"],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            user_id=user_id,
        )
    if status != "connected":
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE integrations.mcp_connections SET status = :s WHERE workspace_id = :ws"
                ),
                {"s": status, "ws": workspace_id},
            )


async def connection_status(engine: AsyncEngine, workspace_id: UUID) -> str:
    async with engine.connect() as conn:
        return str(
            await conn.scalar(
                text("SELECT status FROM integrations.mcp_connections WHERE workspace_id = :ws"),
                {"ws": workspace_id},
            )
        )


def run_context(
    redis: Any,
    sessions: async_sessionmaker[AsyncSession],
    workspace_id: UUID,
    run_id: UUID,
    linear: FakeLinear,
) -> McpRunContext:
    def open_session(ws: UUID) -> Any:
        return in_workspace(sessions, ws)

    return McpRunContext(
        workspace_id=workspace_id,
        run_id=run_id,
        open_session=open_session,
        redis=redis,
        make_client=oauth_client(linear),
        mcp_http_client=mcp_client(linear),
    )
