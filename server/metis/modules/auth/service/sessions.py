"""Server-side sessions: create, resolve, log out, log out everywhere.

Every function takes the caller's ``AsyncSession`` and never commits (the caller owns the
transaction). Sessions are not tenant data: no RLS context is needed. The raw token is
never stored or logged; only its SHA-256 hash is.

A session resolves while it is not revoked, ``now < expires_at`` (absolute,
``SESSION_TTL_DAYS``) and ``now - last_seen_at < SESSION_IDLE_DAYS``. Use advances
``last_seen_at`` at most once per :data:`SESSION_TOUCH_INTERVAL`. Postgres goes through
``repo.sessions`` and Redis through ``cache.sessions``; this file calls neither directly.
"""

from __future__ import annotations

import ipaddress
from datetime import datetime, timedelta
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.config import get_settings
from metis.core.errors import MetisError, SessionExpiredError
from metis.core.logging import get_logger
from metis.core.security import hash_session_token, new_session_token
from metis.helpers.time import utcnow
from metis.modules.auth import cache, repo
from metis.modules.auth.dto import (
    ActiveSession,
    NewSession,
    SessionRecord,
    SessionRejection,
    SessionUser,
)
from metis.modules.auth.service import users

SESSION_TOUCH_INTERVAL = timedelta(minutes=5)
MAX_USER_AGENT_LENGTH = 512


def rejection[E: MetisError](
    reason: SessionRejection, error: E, session_id: UUID | None = None
) -> E:
    """Log a refused session (never the token) and return ``error`` for the caller to raise."""
    fields = {"reason": reason.value}
    if session_id is not None:
        fields["session_id"] = str(session_id)
    logger.info("auth.session_rejected", **fields)
    return error


async def create_session(
    session: AsyncSession, user_id: UUID, user_agent: str | None, ip: str | None
) -> NewSession:
    """Start a session for ``user_id``; the returned token goes in the cookie."""
    now = utcnow()
    token = new_session_token()
    record = await repo.sessions.create(
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


async def resolve_session(session: AsyncSession, redis: Redis, token: str) -> ActiveSession:
    """Return the active session for ``token`` or raise ``SessionExpiredError``."""
    now = utcnow()
    token_hash = hash_session_token(token)
    cached = await cache.sessions.read(redis, token_hash)
    if cached.revoked:
        raise rejection(SessionRejection.REVOKED, SessionExpiredError("Session has expired"))
    record = cached.record or await repo.sessions.get_by_hash(session, token_hash)
    if record is None:
        raise rejection(SessionRejection.UNKNOWN, SessionExpiredError("Session not found"))
    reason = _rejection_reason(record, now)
    if reason is not None:
        raise rejection(reason, SessionExpiredError("Session has expired"), record.id)
    needs_cache_write = cached.record is None
    if now - record.last_seen_at >= SESSION_TOUCH_INTERVAL:
        await repo.sessions.touch(session, record.id, now)
        record = record.model_copy(update={"last_seen_at": now})
        needs_cache_write = True
    if needs_cache_write:
        await cache.sessions.write(redis, token_hash, record, now)
    return ActiveSession(session_id=record.id, user_id=record.user_id, expires_at=record.expires_at)


async def logout(session: AsyncSession, redis: Redis, token: str) -> None:
    """Revoke the session for ``token``; unknown or already revoked is a no-op."""
    token_hash = hash_session_token(token)
    session_id = await repo.sessions.revoke(session, token_hash, utcnow())
    if session_id is None:
        return
    await cache.sessions.mark_revoked(redis, [token_hash])
    logger.info("auth.session_revoked", session_id=str(session_id))


async def logout_all(session: AsyncSession, redis: Redis, user_id: UUID) -> int:
    """Revoke every active session of ``user_id``; return how many were revoked."""
    hashes = await repo.sessions.revoke_all_for_user(session, user_id, utcnow())
    await cache.sessions.mark_revoked(redis, hashes)
    logger.info("auth.sessions_revoked_all", user_id=str(user_id), count=len(hashes))
    return len(hashes)


async def get_session_user(session: AsyncSession, active: ActiveSession) -> SessionUser:
    """Load the user behind ``active``."""
    user = await users.get_user(session, active.user_id)
    if user is None:  # sessions cascade on user delete; only a race gets here
        raise rejection(SessionRejection.UNKNOWN, SessionExpiredError("Session not found"))
    return SessionUser(user=user, session_id=active.session_id)


logger = get_logger(__name__)


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


def _rejection_reason(record: SessionRecord, now: datetime) -> SessionRejection | None:
    if record.revoked_at is not None:
        return SessionRejection.REVOKED
    if now >= record.expires_at:
        return SessionRejection.EXPIRED
    if now - record.last_seen_at >= timedelta(days=get_settings().session_idle_days):
        return SessionRejection.IDLE
    return None
