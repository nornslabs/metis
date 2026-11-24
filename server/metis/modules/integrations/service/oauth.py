"""Connecting a provider: start the OAuth round trip, then finish it at the callback.

``start_connect`` discovers the provider's authorization server, registers a client, keeps
the PKCE verifier and the sealed client secret in Redis (``cache.oauth``, single use, 10
minutes) and returns the consent URL. ``finish_connect`` takes that entry back, checks the
signed-in user is the one who started it and still owns the workspace, exchanges the code
and stores the sealed tokens. Failures raise ``IntegrationOAuthStateInvalidError`` or
``IntegrationOAuthFailedError``; no code, state, verifier, token or secret is ever logged.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import SecretStr
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from metis.adapters.mcp import oauth
from metis.core.config import get_settings
from metis.core.db import set_user, set_workspace
from metis.core.errors import (
    IntegrationOAuthFailedError,
    IntegrationOAuthStateInvalidError,
    UpstreamError,
)
from metis.core.logging import get_logger
from metis.core.security import code_challenge, new_code_verifier, new_oauth_value
from metis.helpers.http import ClientFactory
from metis.helpers.redirects import safe_relative_path
from metis.modules.auth import User
from metis.modules.identity import MemberRole, Membership, list_workspaces
from metis.modules.integrations import cache, repo
from metis.modules.integrations.dto import (
    ConnectResult,
    ConnectStarted,
    IntegrationProvider,
    PendingConnect,
)
from metis.modules.integrations.helpers import permissions, sealing, servers
from metis.modules.integrations.helpers.labels import provider_label
from metis.modules.integrations.helpers.sealing import StoredTokens

MAX_STATE_LENGTH = 128
MAX_CODE_LENGTH = 2048
DEFAULT_REDIRECT = "/?settings=integrations"
CALLBACK_PATH = "/v1/integrations/{provider}/callback"

logger = get_logger(__name__)


class ConnectStep(StrEnum):
    """Where in the round trip a failure happened (logged as ``step``)."""

    START = "start"
    CALLBACK = "callback"


async def start_connect(
    redis: Redis,
    make_client: ClientFactory,
    membership: Membership,
    user: User,
    provider: IntegrationProvider,
    redirect_to: str | None,
) -> ConnectStarted:
    """Remember a new connect attempt and return the provider URL to send the browser to."""
    permissions.require_owner(membership, "connect integrations")
    server_url = servers.server_url(provider)
    workspace_id = membership.workspace.id
    redirect_uri = callback_url(provider)
    try:
        metadata = await oauth.discover(make_client, provider.value, server_url)
        client = await oauth.register_client(make_client, provider.value, metadata, redirect_uri)
    except UpstreamError as exc:
        raise _failed(provider, ConnectStep.START, oauth.reason_of(exc)) from None
    state, verifier = new_oauth_value(), new_code_verifier()
    pending = PendingConnect(
        workspace_id=workspace_id,
        user_id=user.id,
        provider=provider,
        client_id=client.client_id,
        sealed_client_secret=(
            sealing.seal_text(client.client_secret.get_secret_value(), workspace_id)
            if client.client_secret
            else None
        ),
        token_endpoint=metadata.token_endpoint,
        revocation_endpoint=metadata.revocation_endpoint,
        code_verifier=verifier,
        redirect_to=safe_relative_path(redirect_to) if redirect_to else DEFAULT_REDIRECT,
        scopes=[],
    )
    try:
        await cache.oauth.save_pending(redis, state, pending)
    except RedisError:
        raise _failed(provider, ConnectStep.START, "state_store_unavailable") from None
    url = oauth.authorization_url(
        metadata,
        client,
        redirect_uri=redirect_uri,
        state=state,
        code_challenge=code_challenge(verifier),
        resource=server_url,
        scopes=pending.scopes,
    )
    return ConnectStarted(authorize_url=url)


async def finish_connect(
    session: AsyncSession,
    redis: Redis,
    make_client: ClientFactory,
    user: User,
    provider: IntegrationProvider,
    *,
    code: str | None,
    state: str | None,
    error: str | None,
) -> ConnectResult:
    """Finish the attempt ``state`` started; the caller commits (or rolls back on an error).

    The attempt is consumed first, so a replayed callback never connects anything.
    """
    server_url = servers.server_url(provider)
    pending = await _take_pending(redis, state)
    if pending.provider is not provider:
        raise _state_invalid("other_provider")
    if pending.user_id != user.id:
        raise _state_invalid("other_user")
    await _require_owner_now(session, user, pending)
    if error:
        raise _failed(provider, ConnectStep.CALLBACK, "provider_error")
    if not code or len(code) > MAX_CODE_LENGTH:
        raise _failed(provider, ConnectStep.CALLBACK, "missing_code")
    tokens, stored = await _exchange(make_client, pending, code, server_url)
    workspace_id = pending.workspace_id
    row = await repo.connections.upsert_connected(
        session,
        workspace_id,
        provider,
        server_url=server_url,
        sealed_tokens=sealing.seal_tokens(stored, workspace_id),
        scopes=tokens.scopes,
        expires_at=tokens.expires_at,
        user_id=user.id,
    )
    logger.info(
        "integration.connected",
        provider=provider.value,
        workspace_id=str(workspace_id),
        version=row.version,
    )
    await _verify(make_client, provider, tokens.access_token.get_secret_value())
    return ConnectResult(provider=provider, redirect_to=pending.redirect_to)


def callback_url(provider: IntegrationProvider) -> str:
    """The redirect URI registered with the provider: on the web origin, through its
    ``/v1`` rewrite, so the browser's session cookie reaches the callback."""
    base = get_settings().web_base_url.rstrip("/")
    return base + CALLBACK_PATH.format(provider=provider.value)


async def _exchange(
    make_client: ClientFactory, pending: PendingConnect, code: str, server_url: str
) -> tuple[oauth.TokenSet, StoredTokens]:
    """Trade ``code`` for tokens; also the storable form (tokens + the registered client)."""
    provider = pending.provider
    client = oauth.RegisteredClient(
        client_id=pending.client_id,
        client_secret=(
            SecretStr(sealing.open_text(pending.sealed_client_secret, pending.workspace_id))
            if pending.sealed_client_secret
            else None
        ),
    )
    try:
        tokens = await oauth.exchange_code(
            make_client,
            provider.value,
            token_endpoint=pending.token_endpoint,
            client=client,
            code=code,
            code_verifier=pending.code_verifier,
            redirect_uri=callback_url(provider),
            resource=server_url,
        )
    except UpstreamError as exc:
        raise _failed(provider, ConnectStep.CALLBACK, oauth.reason_of(exc)) from None
    stored = StoredTokens(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        client_id=client.client_id,
        client_secret=client.client_secret,
        token_endpoint=pending.token_endpoint,
        revocation_endpoint=pending.revocation_endpoint,
    )
    return tokens, stored


async def _verify(
    make_client: ClientFactory, provider: IntegrationProvider, access_token: str
) -> None:
    """One tool listing proves the new connection works; a failure is logged, not raised
    (the user sees it on the tools list)."""
    try:
        await servers.list_tools(make_client, provider, access_token)
    except UpstreamError as exc:
        logger.warning(
            "integration.verify_failed", provider=provider.value, reason=oauth.reason_of(exc)
        )


async def _take_pending(redis: Redis, state: str | None) -> PendingConnect:
    if not state or len(state) > MAX_STATE_LENGTH:
        raise _state_invalid("missing")
    try:
        pending = await cache.oauth.take_pending(redis, state)
    except RedisError:
        raise IntegrationOAuthFailedError(
            "The connection could not be completed. Please try again."
        ) from None
    if pending is None:
        raise _state_invalid("unknown")
    return pending


async def _require_owner_now(session: AsyncSession, user: User, pending: PendingConnect) -> None:
    """The user must still own the workspace; then scope RLS to it for the write."""
    memberships = await list_workspaces(session, user)
    membership = next((m for m in memberships if m.workspace.id == pending.workspace_id), None)
    if membership is None or membership.role is not MemberRole.OWNER:
        raise _state_invalid("not_owner")
    await set_user(session, user.id)
    await set_workspace(session, pending.workspace_id)


def _state_invalid(why: str) -> IntegrationOAuthStateInvalidError:
    logger.info("integration.oauth_state_rejected", reason=why)
    return IntegrationOAuthStateInvalidError("This connect link is invalid or has expired")


def _failed(
    provider: IntegrationProvider, step: ConnectStep, reason: str
) -> IntegrationOAuthFailedError:
    logger.warning(
        "integration.oauth_failed", provider=provider.value, step=step.value, reason=reason
    )
    return IntegrationOAuthFailedError(
        f"Connecting {provider_label(provider)} failed. Please try again.",
        meta={"provider": provider.value, "reason": reason},
    )
