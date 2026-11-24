"""Using a connection's tokens: open them, refresh them shortly before they expire, and mark
the connection ``expired`` when the provider no longer accepts them.

Every function takes the caller's ``AsyncSession`` and flushes but never commits. A refresh
spends a single-use refresh token, so callers must commit right after it (and must not roll
the transaction back, or the new token is lost). Concurrent refreshes of one connection are
serialized by the row lock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.adapters.mcp import oauth
from metis.core.db import set_workspace
from metis.core.errors import (
    IntegrationNotConnectedError,
    UpstreamError,
)
from metis.core.logging import get_logger
from metis.helpers.http import ClientFactory, FailureReason
from metis.modules.integrations import repo
from metis.modules.integrations.dto import ConnectionStatus, IntegrationProvider
from metis.modules.integrations.helpers import sealing, servers
from metis.modules.integrations.helpers.labels import expired_error, provider_label
from metis.modules.integrations.helpers.sealing import StoredTokens
from metis.modules.integrations.models import McpConnectionRow

REFRESH_WINDOW = timedelta(seconds=60)
# A refresh the provider answered with a refusal; anything else (timeout, outage) is transient.
_REJECTED = frozenset({FailureReason.UNAUTHORIZED.value, FailureReason.BAD_RESPONSE.value})

logger = get_logger(__name__)


async def get_fresh_token(
    session: AsyncSession,
    make_client: ClientFactory,
    workspace_id: UUID,
    provider: IntegrationProvider,
    *,
    force: bool = False,
) -> str:
    """An access token that is valid now, refreshing first when it expires within
    :data:`REFRESH_WINDOW` (or always, with ``force``).

    Raises ``IntegrationNotConnectedError`` (no live connection) and
    ``IntegrationExpiredError`` (the tokens no longer work; the row is marked ``expired``).
    A transient provider failure while refreshing raises ``UpstreamError`` and changes nothing.
    """
    await set_workspace(session, workspace_id)
    row = await repo.connections.get(session, workspace_id, provider)
    row, tokens = _require_usable(row, workspace_id, provider)
    if not force and not _needs_refresh(row.expires_at):
        return tokens.access_token.get_secret_value()
    # Only a refresh takes the row lock, so plain reads never queue behind one. Re-read under
    # the lock: another request may have refreshed while this one waited.
    row, tokens = _require_usable(
        await repo.connections.get(session, workspace_id, provider, lock=True),
        workspace_id,
        provider,
    )
    if not force and not _needs_refresh(row.expires_at):
        return tokens.access_token.get_secret_value()
    refreshed = await _refresh(session, make_client, row, tokens, provider)
    return refreshed.access_token.get_secret_value()


async def mark_expired(
    session: AsyncSession, workspace_id: UUID, provider: IntegrationProvider
) -> None:
    """Mark a live connection ``expired`` (the provider rejected its tokens)."""
    row = await repo.connections.get(session, workspace_id, provider, lock=True)
    if row is not None and row.status == ConnectionStatus.CONNECTED.value:
        await repo.connections.mark_expired(session, row.id)
        logger.info("integration.expired", provider=provider.value, workspace_id=str(workspace_id))


def is_rejected(exc: UpstreamError) -> bool:
    """Whether ``exc`` means the provider refused the credentials (not an outage)."""
    return oauth.reason_of(exc) in _REJECTED


def _require_usable(
    row: McpConnectionRow | None, workspace_id: UUID, provider: IntegrationProvider
) -> tuple[McpConnectionRow, StoredTokens]:
    if row is None or row.status == ConnectionStatus.REVOKED.value or row.sealed_tokens is None:
        raise IntegrationNotConnectedError(
            f"{provider_label(provider)} is not connected", meta={"provider": provider.value}
        )
    if row.status == ConnectionStatus.EXPIRED.value:
        raise expired_error(provider)
    return row, sealing.open_tokens(row.sealed_tokens, workspace_id)


def _is_past(expires_at: datetime | None) -> bool:
    return expires_at is not None and expires_at <= datetime.now(UTC)


def _needs_refresh(expires_at: datetime | None) -> bool:
    return expires_at is not None and expires_at - datetime.now(UTC) <= REFRESH_WINDOW


async def _refresh(
    session: AsyncSession,
    make_client: ClientFactory,
    row: McpConnectionRow,
    tokens: StoredTokens,
    provider: IntegrationProvider,
) -> StoredTokens:
    expired = expired_error(provider)
    if tokens.refresh_token is None:
        if not _is_past(row.expires_at):
            return tokens  # still valid, and there is nothing to refresh it with
        await repo.connections.mark_expired(session, row.id)
        logger.info("integration.expired", provider=provider.value, reason="no_refresh_token")
        raise expired
    client = oauth.RegisteredClient(client_id=tokens.client_id, client_secret=tokens.client_secret)
    try:
        new = await oauth.refresh(
            make_client,
            provider.value,
            token_endpoint=tokens.token_endpoint,
            client=client,
            refresh_token=tokens.refresh_token.get_secret_value(),
            resource=servers.server_url(provider),
        )
    except UpstreamError as exc:
        if not is_rejected(exc):
            raise
        await repo.connections.mark_expired(session, row.id)
        logger.info("integration.expired", provider=provider.value, reason=oauth.reason_of(exc))
        raise expired from None
    stored = StoredTokens(
        access_token=new.access_token,
        # Some servers keep the old refresh token and send none back.
        refresh_token=new.refresh_token or tokens.refresh_token,
        client_id=tokens.client_id,
        client_secret=tokens.client_secret,
        token_endpoint=tokens.token_endpoint,
        revocation_endpoint=tokens.revocation_endpoint,
    )
    await repo.connections.replace_tokens(
        session,
        row.id,
        sealed_tokens=sealing.seal_tokens(stored, row.workspace_id),
        scopes=new.scopes or list(row.scopes),
        expires_at=new.expires_at,
    )
    logger.info("integration.refreshed", provider=provider.value)
    return stored


def _label(provider: IntegrationProvider) -> str:
    return provider.value.capitalize()
