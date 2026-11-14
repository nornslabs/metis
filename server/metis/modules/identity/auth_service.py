"""Server-side sessions: create, resolve, log out, log out everywhere.

Every function takes the caller's ``AsyncSession`` and never commits (the
caller owns the transaction). Sessions are not tenant data: no RLS context is
needed. The raw token is never stored or logged; only its SHA-256 hash is.

A session resolves while it is not revoked, ``now < expires_at`` (absolute,
``SESSION_TTL_DAYS``) and ``now - last_seen_at < SESSION_IDLE_DAYS``. Use
advances ``last_seen_at`` at most once per :data:`SESSION_TOUCH_INTERVAL`.
``sign_in`` turns a verified provider profile into a user: by
``(provider, subject)``, else by a legacy ``users.auth_sub`` or the same email
(linking a new identity), else a new user with a personal workspace.

Internal to identity: the auth routes and ``auth_deps`` call it.
"""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime, timedelta
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.config import get_settings
from metis.core.errors import (
    EmailUnverifiedError,
    InvalidInputError,
    MetisError,
    SessionExpiredError,
)
from metis.core.logging import get_logger
from metis.core.security import hash_session_token, new_session_token
from metis.helpers.validation import validate_input
from metis.modules.identity import identities_repo, repo, service, sessions_repo
from metis.modules.identity.models import UserRow
from metis.modules.identity.providers.base import (
    AuthProviderName,
    OAuthFailure,
    OAuthStep,
    ProviderProfile,
    oauth_failed,
)
from metis.modules.identity.schemas import (
    ActiveSession,
    NewSession,
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
    record = await sessions_repo.insert_session(
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
    cached = await sessions_repo.read_cached(redis, token_hash)
    if cached.revoked:
        raise rejection(SessionRejection.REVOKED, SessionExpiredError("Session has expired"))
    record = cached.record or await sessions_repo.get_session_by_hash(session, token_hash)
    if record is None:
        raise rejection(SessionRejection.UNKNOWN, SessionExpiredError("Session not found"))
    reason = _rejection_reason(record, now)
    if reason is not None:
        raise rejection(reason, SessionExpiredError("Session has expired"), record.id)
    needs_cache_write = cached.record is None
    if now - record.last_seen_at >= SESSION_TOUCH_INTERVAL:
        await sessions_repo.touch_session(session, record.id, now)
        record = record.model_copy(update={"last_seen_at": now})
        needs_cache_write = True
    if needs_cache_write:
        await sessions_repo.write_cached(redis, token_hash, record, now)
    return ActiveSession(session_id=record.id, user_id=record.user_id, expires_at=record.expires_at)


async def logout(session: AsyncSession, redis: Redis, token: str) -> None:
    """Revoke the session for ``token``; unknown or already revoked is a no-op."""
    token_hash = hash_session_token(token)
    session_id = await sessions_repo.revoke_session(session, token_hash, _now())
    if session_id is None:
        return
    await sessions_repo.mark_revoked(redis, [token_hash])
    logger.info("auth.session_revoked", session_id=str(session_id))


async def logout_all(session: AsyncSession, redis: Redis, user_id: UUID) -> int:
    """Revoke every active session of ``user_id``; return how many were revoked."""
    hashes = await sessions_repo.revoke_user_sessions(session, user_id, _now())
    await sessions_repo.mark_revoked(redis, hashes)
    logger.info("auth.sessions_revoked_all", user_id=str(user_id), count=len(hashes))
    return len(hashes)


async def get_session_user(session: AsyncSession, active: ActiveSession) -> SessionUser:
    """Load the user behind ``active`` and their personal workspace."""
    row = await repo.get_user(session, active.user_id)
    if row is None:  # sessions cascade on user delete; only a race gets here
        raise rejection(SessionRejection.UNKNOWN, SessionExpiredError("Session not found"))
    user = User.model_validate(row)
    personal = await service.ensure_personal_workspace(session, user)
    return SessionUser(user=user, personal_workspace=personal, session_id=active.session_id)


# --------------------------------------------------------------------- sign-in
def _claims(profile: ProviderProfile) -> UserClaims:
    """Validate the profile like any user input; a malformed one fails the sign-in."""
    try:
        return validate_input(
            UserClaims,
            sub=profile.subject,
            email=profile.email,
            name=profile.name,
            image=profile.avatar_url,
        )
    except InvalidInputError:
        raise oauth_failed(profile.provider, OAuthStep.SIGN_IN, OAuthFailure.BAD_RESPONSE) from None


async def _find_user_to_link(
    session: AsyncSession, profile: ProviderProfile, claims: UserClaims
) -> UserRow | None:
    # Accounts created through Auth.js keyed on the Google subject (until SHIP-267).
    if profile.provider is AuthProviderName.GOOGLE:
        row = await repo.get_user_by_auth_sub(session, claims.sub)
        if row is not None:
            return row
    return await repo.get_user_by_email(session, claims.email)


async def _user_for(
    session: AsyncSession, profile: ProviderProfile, claims: UserClaims
) -> tuple[UserRow, SignInOutcome] | None:
    """The user to link this new identity to, creating one if needed; ``None`` on a race."""
    linked = await _find_user_to_link(session, profile, claims)
    if linked is not None:
        return linked, SignInOutcome.LINKED
    created = await repo.insert_user(session, claims)
    return None if created is None else (created, SignInOutcome.CREATED)


async def _signed_in(session: AsyncSession, row: UserRow, outcome: SignInOutcome) -> SignedIn:
    user = User.model_validate(row)
    personal = await service.ensure_personal_workspace(session, user)
    return SignedIn(user=user, personal_workspace=personal, outcome=outcome)


async def _try_sign_in(
    session: AsyncSession, profile: ProviderProfile, claims: UserClaims, now: datetime
) -> SignedIn | None:
    identity = await identities_repo.get_identity(session, profile.provider, profile.subject)
    if identity is not None:
        await identities_repo.record_login(
            session, identity.id, email=claims.email, email_verified=profile.email_verified, now=now
        )
        row = await repo.get_user(session, identity.user_id)
        return None if row is None else await _signed_in(session, row, SignInOutcome.EXISTING)
    found = await _user_for(session, profile, claims)
    if found is None:
        return None
    row, outcome = found
    inserted = await identities_repo.insert_identity(
        session,
        user_id=row.id,
        provider=profile.provider,
        subject=profile.subject,
        email=claims.email,
        email_verified=profile.email_verified,
        now=now,
    )
    return None if inserted is None else await _signed_in(session, row, outcome)


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
