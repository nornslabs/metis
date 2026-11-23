"""Reading and ending connections, listing a server's tools and building the agent's client.

Every function takes the caller's ``AsyncSession``, flushes but never commits.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import McpHttpClientFactory
from sqlalchemy.ext.asyncio import AsyncSession

from metis.adapters.mcp import oauth
from metis.adapters.mcp.client import McpServer, build_mcp_client
from metis.core.db import set_workspace
from metis.core.errors import (
    IntegrationExpiredError,
    IntegrationNotFoundError,
    MetisError,
    SecretDecryptError,
    UpstreamError,
)
from metis.core.logging import get_logger
from metis.helpers.http import ClientFactory, FailureReason
from metis.modules.identity import Membership
from metis.modules.integrations import repo
from metis.modules.integrations.dto import (
    ConnectionStatus,
    IntegrationProvider,
    IntegrationStatus,
    IntegrationView,
    ToolInfo,
)
from metis.modules.integrations.helpers import permissions, sealing, servers
from metis.modules.integrations.helpers.labels import expired_error, provider_label
from metis.modules.integrations.helpers.sealing import StoredTokens
from metis.modules.integrations.models import McpConnectionRow
from metis.modules.integrations.service import tokens

logger = get_logger(__name__)

_STATUS_OF = {
    ConnectionStatus.CONNECTED.value: IntegrationStatus.CONNECTED,
    ConnectionStatus.EXPIRED.value: IntegrationStatus.EXPIRED,
}


@dataclass(frozen=True)
class ToolListing:
    """Outcome of ``list_tools``: the tools, or the failure to return (not raise) so a
    connection marked ``expired`` still commits."""

    tools: list[ToolInfo]
    error: MetisError | None = None


async def list_integrations(session: AsyncSession, workspace_id: UUID) -> list[IntegrationView]:
    """One entry per supported provider; a missing or revoked connection reads as
    ``not_connected``. Never carries a token or a secret."""
    await set_workspace(session, workspace_id)
    rows = {row.provider: row for row in await repo.connections.list_all(session, workspace_id)}
    return [_view(provider, rows.get(provider.value)) for provider in servers.supported_providers()]


async def list_tools(
    session: AsyncSession,
    make_client: ClientFactory,
    workspace_id: UUID,
    provider: IntegrationProvider,
) -> ToolListing:
    """The tools the connected server offers to this workspace.

    A rejected token is refreshed once; if it is still rejected the connection is marked
    ``expired`` and the listing carries ``IntegrationExpiredError``.
    """
    servers.server_url(provider)
    try:
        token = await tokens.get_fresh_token(session, make_client, workspace_id, provider)
        return ToolListing(tools=await servers.list_tools(make_client, provider, token))
    except IntegrationExpiredError as exc:
        return ToolListing(tools=[], error=exc)
    except UpstreamError as exc:
        # Returned, not raised: a refresh above already spent the single-use refresh token,
        # and the new one must commit.
        if oauth.reason_of(exc) != FailureReason.UNAUTHORIZED.value:
            return ToolListing(tools=[], error=exc)
    return await _retry_after_refresh(session, make_client, workspace_id, provider)


async def disconnect(
    session: AsyncSession,
    make_client: ClientFactory,
    membership: Membership,
    provider: IntegrationProvider,
) -> None:
    """Revoke the connection (owners only): the provider is told (best effort), the tokens
    are wiped and the row kept as ``revoked``. None to disconnect → 404."""
    permissions.require_owner(membership, "disconnect integrations")
    workspace_id = membership.workspace.id
    await set_workspace(session, workspace_id)
    row = await repo.connections.get(session, workspace_id, provider, lock=True)
    if row is None or row.sealed_tokens is None:
        raise IntegrationNotFoundError(
            f"{provider_label(provider)} is not connected", meta={"provider": provider.value}
        )
    stored = _readable_tokens(row, workspace_id)
    await repo.connections.mark_revoked(session, row.id)
    if stored is not None and stored.revocation_endpoint is not None:
        await oauth.revoke(
            make_client,
            provider.value,
            revocation_endpoint=stored.revocation_endpoint,
            client=oauth.RegisteredClient(
                client_id=stored.client_id, client_secret=stored.client_secret
            ),
            token=(stored.refresh_token or stored.access_token).get_secret_value(),
        )
    logger.info("integration.disconnected", provider=provider.value, workspace_id=str(workspace_id))


async def get_mcp_client(
    session: AsyncSession,
    make_client: ClientFactory,
    workspace_id: UUID,
    providers: Sequence[IntegrationProvider],
    *,
    httpx_client_factory: McpHttpClientFactory | None = None,
) -> MultiServerMCPClient:
    """A tool client for the connected ``providers``, each with a fresh bearer token.

    The only way agent code gets an MCP client; only workers call it. Raises
    ``IntegrationNotConnectedError`` / ``IntegrationExpiredError`` naming the provider. The
    caller commits right after (a refresh spends a single-use refresh token); on
    ``IntegrationExpiredError`` the row is already marked ``expired``, so commit before failing.
    """
    connections: dict[str, McpServer] = {}
    for provider in providers:
        token = await tokens.get_fresh_token(session, make_client, workspace_id, provider)
        connections[provider.value] = McpServer(servers.server_url(provider), token)
    return build_mcp_client(connections, httpx_client_factory)


async def _retry_after_refresh(
    session: AsyncSession,
    make_client: ClientFactory,
    workspace_id: UUID,
    provider: IntegrationProvider,
) -> ToolListing:
    try:
        token = await tokens.get_fresh_token(
            session, make_client, workspace_id, provider, force=True
        )
        return ToolListing(tools=await servers.list_tools(make_client, provider, token))
    except IntegrationExpiredError as exc:
        return ToolListing(tools=[], error=exc)
    except UpstreamError as exc:
        if oauth.reason_of(exc) != FailureReason.UNAUTHORIZED.value:
            return ToolListing(tools=[], error=exc)
    await tokens.mark_expired(session, workspace_id, provider)
    return ToolListing(tools=[], error=expired_error(provider))


def _readable_tokens(row: McpConnectionRow, workspace_id: UUID) -> StoredTokens | None:
    """The row's tokens, or ``None`` when they cannot be read: a broken connection must
    still be disconnectable, only the provider-side revocation is skipped."""
    try:
        return sealing.open_tokens(row.sealed_tokens or {}, workspace_id)
    except SecretDecryptError:
        logger.warning("integration.tokens_unreadable", workspace_id=str(workspace_id))
        return None


def _view(provider: IntegrationProvider, row: McpConnectionRow | None) -> IntegrationView:
    status = _STATUS_OF.get(row.status, IntegrationStatus.NOT_CONNECTED) if row else None
    if row is None or status is None:
        return IntegrationView(provider=provider, status=IntegrationStatus.NOT_CONNECTED)
    return IntegrationView(
        provider=provider,
        status=status,
        scopes=list(row.scopes),
        expires_at=row.expires_at,
        connected_at=row.connected_at,
        connected_by=row.created_by,
        version=row.version,
    )
