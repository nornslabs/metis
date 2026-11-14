"""Server-side sessions: create, resolve, log out, log out everywhere.

Every function takes the caller's ``AsyncSession`` and never commits (the
caller owns the transaction). Sessions are not tenant data: no RLS context is
needed. The raw token is never stored or logged; only its SHA-256 hash is.

A session resolves while it is not revoked, ``now < expires_at`` (absolute,
``SESSION_TTL_DAYS``) and ``now - last_seen_at < SESSION_IDLE_DAYS``. Use
advances ``last_seen_at`` at most once per :data:`SESSION_TOUCH_INTERVAL`.
Internal to identity: the auth routes (SHIP-265) and ``auth_deps`` call it.
"""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime, timedelta
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.config import get_settings
from metis.core.errors import MetisError, SessionExpiredError
from metis.core.logging import get_logger
from metis.core.security import hash_session_token, new_session_token
from metis.modules.identity import repo, service, sessions_repo
from metis.modules.identity.schemas import (
    ActiveSession,
    NewSession,
    SessionRecord,
    SessionRejection,
    SessionUser,
    User,
)

SESSION_TOUCH_INTERVAL = timedelta(minutes=5)
MAX_USER_AGENT_LENGTH = 512

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
