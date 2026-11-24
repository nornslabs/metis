"""Migration ``0023_integrations``: RLS and the constraints that keep a connection valid."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.helpers.ids import uuid7
from tests.helpers.auth import SESSION_COOKIE, sign_in

TABLES = ("mcp_connections", "external_refs", "export_jobs")
INSERT_CONNECTION = (
    "INSERT INTO integrations.mcp_connections "
    "(id, workspace_id, provider, server_url, status, sealed_tokens, created_by) "
    "VALUES (:id, :ws, :provider, 'https://mcp.example/mcp', :status, "
    "CAST(:tokens AS jsonb), :user)"
)


async def _execute(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)


async def _owner_and_workspace(client: httpx.AsyncClient, engine: AsyncEngine) -> tuple[UUID, UUID]:
    token = await sign_in(engine)
    current = await client.get(
        "/v1/workspaces/current", headers={"Cookie": f"{SESSION_COOKIE}={token}"}
    )
    workspace = UUID(current.json()["workspace"]["id"])
    async with engine.connect() as conn:
        user = await conn.scalar(
            text("SELECT created_by FROM identity.workspaces WHERE id = :w"), {"w": workspace}
        )
    return user, workspace


async def test_every_integrations_table_has_row_level_security(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'integrations' AND relkind = 'r'"
                )
            )
        ).all()

    assert {row[0]: (row[1], row[2]) for row in rows} == dict.fromkeys(TABLES, (True, True))


async def test_a_workspace_has_one_connection_per_provider(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    user, workspace = await _owner_and_workspace(client, engine)
    values = {
        "ws": workspace,
        "provider": "linear",
        "status": "expired",
        "tokens": "{}",
        "user": user,
    }
    await _execute(engine, INSERT_CONNECTION, id=uuid7(), **values)

    with pytest.raises(IntegrityError, match="uq_mcp_connections_workspace_provider"):
        await _execute(engine, INSERT_CONNECTION, id=uuid7(), **values)


async def test_a_revoked_connection_has_no_tokens_and_a_live_one_has(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    user, workspace = await _owner_and_workspace(client, engine)
    base = {"ws": workspace, "provider": "linear", "user": user}

    with pytest.raises(IntegrityError, match="ck_mcp_connections_tokens_revoked"):
        await _execute(engine, INSERT_CONNECTION, id=uuid7(), status="revoked", tokens="{}", **base)
    with pytest.raises(IntegrityError, match="ck_mcp_connections_tokens_revoked"):
        await _execute(
            engine,
            INSERT_CONNECTION.replace("CAST(:tokens AS jsonb)", "NULL"),
            id=uuid7(),
            status="connected",
            **base,
        )


async def test_the_database_refuses_an_unknown_provider_or_status(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    user, workspace = await _owner_and_workspace(client, engine)

    with pytest.raises(IntegrityError, match="ck_mcp_connections_provider"):
        await _execute(
            engine,
            INSERT_CONNECTION,
            id=uuid7(),
            ws=workspace,
            provider="jira",
            status="connected",
            tokens="{}",
            user=user,
        )
    with pytest.raises(IntegrityError, match="ck_mcp_connections_status"):
        await _execute(
            engine,
            INSERT_CONNECTION,
            id=uuid7(),
            ws=workspace,
            provider="linear",
            status="paused",
            tokens="{}",
            user=user,
        )


async def test_an_external_ref_is_unique_per_workspace_provider_and_local_record(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    _, workspace = await _owner_and_workspace(client, engine)
    insert = (
        "INSERT INTO integrations.external_refs "
        "(id, workspace_id, provider, local_kind, local_id, external_id) "
        "VALUES (:id, :ws, 'linear', 'task', :local, 'LIN-1')"
    )
    local = uuid7()
    await _execute(engine, insert, id=uuid7(), ws=workspace, local=local)

    with pytest.raises(IntegrityError, match="uq_external_refs_local"):
        await _execute(engine, insert, id=uuid7(), ws=workspace, local=local)
