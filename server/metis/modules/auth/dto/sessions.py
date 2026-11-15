"""Session DTOs: stored records, cache lookups, new and active sessions, refusals."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from metis.helpers.dto import FrozenModel
from metis.modules.auth.dto.users import User


class SessionRecord(FrozenModel):
    """A stored session's state: what resolving a token checks (also the cache entry)."""

    id: UUID
    user_id: UUID
    expires_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None = None


class CacheLookup(FrozenModel):
    """Result of a session cache lookup: revoked, a record, or a miss (neither)."""

    revoked: bool = False
    record: SessionRecord | None = None


class SessionRejection(StrEnum):
    """Why a session cookie was refused (logged as ``reason``)."""

    MISSING = "missing"
    UNKNOWN = "unknown"
    EXPIRED = "expired"
    IDLE = "idle"
    REVOKED = "revoked"
    CSRF = "csrf"


class NewSession(FrozenModel):
    """A session just created; ``token`` goes in the cookie and is never stored."""

    token: str
    session_id: UUID
    expires_at: datetime


class ActiveSession(FrozenModel):
    """A session that resolved: not revoked, not expired, not idle."""

    session_id: UUID
    user_id: UUID
    expires_at: datetime


class SessionUser(FrozenModel):
    """The signed-in user and the session in use."""

    user: User
    session_id: UUID
