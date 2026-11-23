"""Postgres access for ``integrations.mcp_connections``. Queries only; no business rules."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.ids import uuid7
from metis.modules.integrations.dto import ConnectionStatus, IntegrationProvider
from metis.modules.integrations.models import McpConnectionRow


async def get(
    session: AsyncSession,
    workspace_id: UUID,
    provider: IntegrationProvider,
    *,
    lock: bool = False,
) -> McpConnectionRow | None:
    """The workspace's connection to ``provider``; ``lock`` takes the row lock (``FOR UPDATE``)
    so concurrent refreshes of a single-use refresh token are serialized."""
    stmt = select(McpConnectionRow).where(
        McpConnectionRow.workspace_id == workspace_id,
        McpConnectionRow.provider == provider.value,
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def list_all(session: AsyncSession, workspace_id: UUID) -> list[McpConnectionRow]:
    """Every connection of the workspace."""
    rows = await session.scalars(
        select(McpConnectionRow).where(McpConnectionRow.workspace_id == workspace_id)
    )
    return list(rows)


async def upsert_connected(
    session: AsyncSession,
    workspace_id: UUID,
    provider: IntegrationProvider,
    *,
    server_url: str,
    sealed_tokens: dict[str, Any],
    scopes: list[str],
    expires_at: datetime | None,
    user_id: UUID,
) -> McpConnectionRow:
    """Create the connection or replace a previous one (any state) with a connected one."""
    values = {
        "server_url": server_url,
        "status": ConnectionStatus.CONNECTED.value,
        "sealed_tokens": sealed_tokens,
        "scopes": scopes,
        "expires_at": expires_at,
        "created_by": user_id,
    }
    stmt = (
        insert(McpConnectionRow)
        .values(id=uuid7(), workspace_id=workspace_id, provider=provider.value, **values)
        .on_conflict_do_update(
            index_elements=[McpConnectionRow.workspace_id, McpConnectionRow.provider],
            set_={
                **values,
                "version": McpConnectionRow.version + 1,
                "connected_at": func.now(),
                "updated_at": func.now(),
            },
        )
        .returning(McpConnectionRow)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one()


async def replace_tokens(
    session: AsyncSession,
    row_id: UUID,
    *,
    sealed_tokens: dict[str, Any],
    scopes: list[str],
    expires_at: datetime | None,
) -> None:
    """Store refreshed tokens on a connected row and bump ``version``."""
    await session.execute(
        update(McpConnectionRow)
        .where(McpConnectionRow.id == row_id)
        .values(
            sealed_tokens=sealed_tokens,
            scopes=scopes,
            expires_at=expires_at,
            version=McpConnectionRow.version + 1,
            updated_at=func.now(),
        )
        .execution_options(synchronize_session="fetch")
    )


async def mark_expired(session: AsyncSession, row_id: UUID) -> None:
    """The tokens no longer work; keep them sealed so a reconnect replaces them."""
    await _set_status(session, row_id, ConnectionStatus.EXPIRED, wipe=False)


async def mark_revoked(session: AsyncSession, row_id: UUID) -> None:
    """Wipe the tokens and mark the connection revoked."""
    await _set_status(session, row_id, ConnectionStatus.REVOKED, wipe=True)


async def _set_status(
    session: AsyncSession, row_id: UUID, status: ConnectionStatus, *, wipe: bool
) -> None:
    values: dict[str, Any] = {
        "status": status.value,
        "version": McpConnectionRow.version + 1,
        "updated_at": func.now(),
    }
    if wipe:
        values.update(sealed_tokens=None, expires_at=None, scopes=[])
    await session.execute(
        update(McpConnectionRow)
        .where(McpConnectionRow.id == row_id)
        .values(**values)
        .execution_options(synchronize_session="fetch")
    )
