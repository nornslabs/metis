"""Auth business rules: server-side sessions, sign-in and the OAuth round trip.

Every function takes the caller's ``AsyncSession`` and never commits (the
caller owns the transaction). Sessions are not tenant data: no RLS context is
needed. The raw token is never stored or logged; only its SHA-256 hash is.

A session resolves while it is not revoked, ``now < expires_at`` (absolute,
``SESSION_TTL_DAYS``) and ``now - last_seen_at < SESSION_IDLE_DAYS``. Use
advances ``last_seen_at`` at most once per :data:`SESSION_TOUCH_INTERVAL`.
``sign_in`` turns a verified provider profile into a user: by
``(provider, subject)``, else by the same email (linking a new identity), else a
new user. The personal workspace is not made here: identity creates it on the
user's first workspace-scoped call.

The OAuth round trip: ``start_login`` keeps the ``nonce``, PKCE
``code_verifier`` and a safe ``redirect_to`` in the login-state cache and
returns the provider URL; ``finish_login`` takes that entry back (single use),
lets the provider verify its answer, signs the user in and opens a session.
Failures raise ``OAuthStateInvalidError``, ``OAuthFailedError`` or
``EmailUnverifiedError``; none of the random values is ever logged.

Postgres goes through ``repo`` and Redis through ``cache``; this module never
calls either store directly.

``get_user`` and ``find_user_by_email`` are public (re-exported by
``metis.modules.auth``); everything else is internal to auth.
"""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime, timedelta
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.config import get_settings
from metis.core.errors import (
    EmailUnverifiedError,
    InvalidInputError,
    MetisError,
    OAuthStateInvalidError,
    SessionExpiredError,
)
from metis.core.logging import get_logger
from metis.core.security import (
    code_challenge,
    hash_session_token,
    new_code_verifier,
    new_oauth_value,
    new_session_token,
)
from metis.helpers.redirects import safe_relative_path
from metis.helpers.text import normalise_email
from metis.helpers.validation import validate_input
from metis.modules.auth import cache, repo
from metis.modules.auth.models import UserRow
from metis.modules.auth.providers.base import (
    AuthProvider,
    OAuthFailure,
    OAuthStep,
    ProviderProfile,
    oauth_failed,
)
from metis.modules.auth.schemas import (
    ActiveSession,
    FinishedLogin,
    NewSession,
    PendingLogin,
    SessionRecord,
    SessionRejection,
    SessionUser,
    SignedIn,
    SignInOutcome,
    User,
    UserClaims,
)

SESSION_TOUCH_INTERVAL = timedelta(minutes=5)
MAX_USER_AGENT_LENGTH = 512
# A concurrent first sign-in can win a unique constraint once; the retry finds its rows.
MAX_SIGN_IN_ATTEMPTS = 2
MAX_STATE_LENGTH = 128
MAX_CODE_LENGTH = 2048

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def rejection[E: MetisError](
    reason: SessionRejection, error: E, session_id: UUID | None = None
) -> E:
    """Log a refused session (never the token) and return ``error`` for the caller to raise."""
    fields = {"reason": reason.value}
    if session_id is not None:
        fields["session_id"] = str(session_id)
    logger.info("auth.session_rejected", **fields)
    return error


def _clean_ip(ip: str | None) -> str | None:
    """Keep ``ip`` only when it is a real IP address (test clients send names)."""
    if ip is None:
        return None
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return None


def _clean_user_agent(user_agent: str | None) -> str | None:
    return user_agent[:MAX_USER_AGENT_LENGTH] if user_agent else None


async def create_session(
    session: AsyncSession, user_id: UUID, user_agent: str | None, ip: str | None
) -> NewSession:
    """Start a session for ``user_id``; the returned token goes in the cookie."""
    now = _now()
    token = new_session_token()
    record = await repo.insert_session(
        session,
        user_id=user_id,
        token_hash=hash_session_token(token),
        now=now,
        expires_at=now + timedelta(days=get_settings().session_ttl_days),
        user_agent=_clean_user_agent(user_agent),
        ip=_clean_ip(ip),
    )
    logger.info("auth.session_created", session_id=str(record.id), user_id=str(user_id))
    return NewSession(token=token, session_id=record.id, expires_at=record.expires_at)


def _rejection_reason(record: SessionRecord, now: datetime) -> SessionRejection | None:
    if record.revoked_at is not None:
        return SessionRejection.REVOKED
    if now >= record.expires_at:
        return SessionRejection.EXPIRED
    if now - record.last_seen_at >= timedelta(days=get_settings().session_idle_days):
        return SessionRejection.IDLE
    return None


async def resolve_session(session: AsyncSession, redis: Redis, token: str) -> ActiveSession:
    """Return the active session for ``token`` or raise ``SessionExpiredError``."""
    now = _now()
    token_hash = hash_session_token(token)
    cached = await cache.read_session(redis, token_hash)
    if cached.revoked:
        raise rejection(SessionRejection.REVOKED, SessionExpiredError("Session has expired"))
    record = cached.record or await repo.get_session_by_hash(session, token_hash)
    if record is None:
        raise rejection(SessionRejection.UNKNOWN, SessionExpiredError("Session not found"))
    reason = _rejection_reason(record, now)
    if reason is not None:
        raise rejection(reason, SessionExpiredError("Session has expired"), record.id)
    needs_cache_write = cached.record is None
    if now - record.last_seen_at >= SESSION_TOUCH_INTERVAL:
        await repo.touch_session(session, record.id, now)
        record = record.model_copy(update={"last_seen_at": now})
        needs_cache_write = True
    if needs_cache_write:
        await cache.write_session(redis, token_hash, record, now)
    return ActiveSession(session_id=record.id, user_id=record.user_id, expires_at=record.expires_at)


async def logout(session: AsyncSession, redis: Redis, token: str) -> None:
    """Revoke the session for ``token``; unknown or already revoked is a no-op."""
    token_hash = hash_session_token(token)
    session_id = await repo.revoke_session(session, token_hash, _now())
    if session_id is None:
        return
    await cache.mark_sessions_revoked(redis, [token_hash])
    logger.info("auth.session_revoked", session_id=str(session_id))


async def logout_all(session: AsyncSession, redis: Redis, user_id: UUID) -> int:
    """Revoke every active session of ``user_id``; return how many were revoked."""
    hashes = await repo.revoke_user_sessions(session, user_id, _now())
    await cache.mark_sessions_revoked(redis, hashes)
    logger.info("auth.sessions_revoked_all", user_id=str(user_id), count=len(hashes))
    return len(hashes)


async def get_session_user(session: AsyncSession, active: ActiveSession) -> SessionUser:
    """Load the user behind ``active``."""
    user = await get_user(session, active.user_id)
    if user is None:  # sessions cascade on user delete; only a race gets here
        raise rejection(SessionRejection.UNKNOWN, SessionExpiredError("Session not found"))
    return SessionUser(user=user, session_id=active.session_id)


# ----------------------------------------------------------------------- users
async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    """The user with ``user_id``, or ``None``."""
    row = await repo.get_user(session, user_id)
    return None if row is None else User.model_validate(row)


async def find_user_by_email(session: AsyncSession, email: str) -> User | None:
    """The user with ``email`` (trimmed, case-insensitive), or ``None``."""
    row = await repo.get_user_by_email(session, normalise_email(email))
    return None if row is None else User.model_validate(row)


# --------------------------------------------------------------------- sign-in
def _claims(profile: ProviderProfile) -> UserClaims:
    """Validate the profile like any user input; a malformed one fails the sign-in."""
    try:
        return validate_input(
            UserClaims,
            email=profile.email,
            name=profile.name,
            image=profile.avatar_url,
        )
    except InvalidInputError:
        raise oauth_failed(profile.provider, OAuthStep.SIGN_IN, OAuthFailure.BAD_RESPONSE) from None


async def _user_for(
    session: AsyncSession, claims: UserClaims
) -> tuple[UserRow, SignInOutcome] | None:
    """The user to link this new identity to, creating one if needed; ``None`` on a race."""
    linked = await repo.get_user_by_email(session, claims.email)
    if linked is not None:
        return linked, SignInOutcome.LINKED
    created = await repo.insert_user(session, claims)
    return None if created is None else (created, SignInOutcome.CREATED)


def _signed_in(row: UserRow, outcome: SignInOutcome) -> SignedIn:
    return SignedIn(user=User.model_validate(row), outcome=outcome)


async def _try_sign_in(
    session: AsyncSession, profile: ProviderProfile, claims: UserClaims, now: datetime
) -> SignedIn | None:
    identity = await repo.get_identity(session, profile.provider, profile.subject)
    if identity is not None:
        await repo.record_login(
            session, identity.id, email=claims.email, email_verified=profile.email_verified, now=now
        )
        row = await repo.get_user(session, identity.user_id)
        return None if row is None else _signed_in(row, SignInOutcome.EXISTING)
    found = await _user_for(session, claims)
    if found is None:
        return None
    row, outcome = found
    inserted = await repo.insert_identity(
        session,
        user_id=row.id,
        provider=profile.provider,
        subject=profile.subject,
        email=claims.email,
        email_verified=profile.email_verified,
        now=now,
    )
    return None if inserted is None else _signed_in(row, outcome)


async def sign_in(session: AsyncSession, profile: ProviderProfile) -> SignedIn:
    """Sign in (or sign up) the user ``profile`` vouches for; the email must be verified."""
    if not profile.email_verified:
        logger.info("auth.sign_in_refused", provider=profile.provider, reason="email_unverified")
        raise EmailUnverifiedError("Your email address is not verified with the provider")
    claims = _claims(profile)
    for _ in range(MAX_SIGN_IN_ATTEMPTS):
        # A lost race must not leave a half-made user behind: undo the whole attempt.
        attempt = await session.begin_nested()
        signed_in = await _try_sign_in(session, profile, claims, _now())
        if signed_in is None:
            await attempt.rollback()
            continue
        await attempt.commit()
        logger.info(
            "auth.sign_in",
            provider=profile.provider,
            outcome=signed_in.outcome.value,
            user_id=str(signed_in.user.id),
        )
        return signed_in
    raise oauth_failed(profile.provider, OAuthStep.SIGN_IN, OAuthFailure.SIGN_IN_CONFLICT)


# ------------------------------------------------------------- oauth sign-in
def _state_invalid(why: str) -> OAuthStateInvalidError:
    logger.info("auth.oauth_state_rejected", reason=why)
    return OAuthStateInvalidError("This sign-in link is invalid or has expired")


async def start_login(redis: Redis, provider: AuthProvider, redirect_to: str | None) -> str:
    """Remember a new login attempt and return the provider URL to send the browser to."""
    state, nonce, verifier = new_oauth_value(), new_oauth_value(), new_code_verifier()
    pending = PendingLogin(
        nonce=nonce, code_verifier=verifier, redirect_to=safe_relative_path(redirect_to)
    )
    url = await provider.authorization_url(state, nonce, code_challenge(verifier))
    try:
        await cache.save_pending_login(redis, state, pending)
    except RedisError:
        raise oauth_failed(
            provider.name, OAuthStep.LOGIN, OAuthFailure.STATE_STORE_UNAVAILABLE
        ) from None
    return url


async def _take_pending(redis: Redis, provider: AuthProvider, state: str | None) -> PendingLogin:
    if not state or len(state) > MAX_STATE_LENGTH:
        raise _state_invalid("missing")
    try:
        pending = await cache.take_pending_login(redis, state)
    except RedisError:
        raise oauth_failed(
            provider.name, OAuthStep.CALLBACK, OAuthFailure.STATE_STORE_UNAVAILABLE
        ) from None
    if pending is None:
        raise _state_invalid("unknown")
    return pending


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
        signed_in = await sign_in(session, profile)
        created = await create_session(session, signed_in.user.id, user_agent, ip)
    return FinishedLogin(token=created.token, redirect_to=pending.redirect_to)
