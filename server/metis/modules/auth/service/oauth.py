"""The browser sign-in round trip: start a login, then finish it at the callback.

``start_login`` keeps the ``nonce``, PKCE ``code_verifier`` and a safe ``redirect_to`` in
the OAuth login-state cache (``cache.oauth``) and returns the provider URL. ``finish_login``
takes that entry back (single use), lets the provider verify its answer, signs the user in
and opens a session. Failures raise ``OAuthStateInvalidError``, ``OAuthFailedError`` or
``EmailUnverifiedError``; none of the random values is ever logged.
"""

from __future__ import annotations

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import OAuthStateInvalidError
from metis.core.logging import get_logger
from metis.core.security import code_challenge, new_code_verifier, new_oauth_value
from metis.helpers.redirects import safe_relative_path
from metis.modules.auth import cache
from metis.modules.auth.dto import FinishedLogin, PendingLogin
from metis.modules.auth.providers.base import AuthProvider, OAuthFailure, OAuthStep, oauth_failed
from metis.modules.auth.service import identities, sessions

MAX_STATE_LENGTH = 128
MAX_CODE_LENGTH = 2048


async def start_login(redis: Redis, provider: AuthProvider, redirect_to: str | None) -> str:
    """Remember a new login attempt and return the provider URL to send the browser to."""
    state, nonce, verifier = new_oauth_value(), new_oauth_value(), new_code_verifier()
    pending = PendingLogin(
        nonce=nonce, code_verifier=verifier, redirect_to=safe_relative_path(redirect_to)
    )
    url = await provider.authorization_url(state, nonce, code_challenge(verifier))
    try:
        await cache.oauth.save_pending(redis, state, pending)
    except RedisError:
        raise oauth_failed(
            provider.name, OAuthStep.LOGIN, OAuthFailure.STATE_STORE_UNAVAILABLE
        ) from None
    return url


async def finish_login(
    session: AsyncSession,
    redis: Redis,
    provider: AuthProvider,
    *,
    code: str | None,
    state: str | None,
    error: str | None,
    user_agent: str | None,
    ip: str | None,
) -> FinishedLogin:
    """Finish the login ``state`` started; the caller commits and sets the cookie.

    On any error the sign-in's writes are rolled back (savepoint), so the
    request's commit stores nothing.
    """
    pending = await _take_pending(redis, provider, state)
    if error:
        raise oauth_failed(provider.name, OAuthStep.CALLBACK, OAuthFailure.PROVIDER_ERROR)
    if not code or len(code) > MAX_CODE_LENGTH:
        raise oauth_failed(provider.name, OAuthStep.CALLBACK, OAuthFailure.MISSING_CODE)
    profile = await provider.complete(code, pending.code_verifier, pending.nonce)
    # A failure past this point leaves nothing behind for the request's commit.
    async with session.begin_nested():
        signed_in = await identities.sign_in(session, profile)
        created = await sessions.create_session(session, signed_in.user.id, user_agent, ip)
    return FinishedLogin(token=created.token, redirect_to=pending.redirect_to)


logger = get_logger(__name__)


def _state_invalid(why: str) -> OAuthStateInvalidError:
    logger.info("auth.oauth_state_rejected", reason=why)
    return OAuthStateInvalidError("This sign-in link is invalid or has expired")


async def _take_pending(redis: Redis, provider: AuthProvider, state: str | None) -> PendingLogin:
    if not state or len(state) > MAX_STATE_LENGTH:
        raise _state_invalid("missing")
    try:
        pending = await cache.oauth.take_pending(redis, state)
    except RedisError:
        raise oauth_failed(
            provider.name, OAuthStep.CALLBACK, OAuthFailure.STATE_STORE_UNAVAILABLE
        ) from None
    if pending is None:
        raise _state_invalid("unknown")
    return pending
