"""Auth DTOs: the user, verified sign-in claims, sessions and sign-in outcomes."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BeforeValidator, Field

from metis.helpers.schemas import Email, FrozenModel
from metis.helpers.text import strip_to_none

MAX_NAME_LENGTH = 200
IMAGE_URL_SCHEMES = ("https://", "http://")


def _check_image_url(value: str | None) -> str | None:
    if value is not None and not value.lower().startswith(IMAGE_URL_SCHEMES):
        raise ValueError("must be an http(s) URL")
    return value


class UserClaims(FrozenModel):
    """A new user's profile from a verified sign-in, validated and normalised."""

    email: Email
    name: Annotated[
        Annotated[str, Field(max_length=MAX_NAME_LENGTH)] | None,
        BeforeValidator(strip_to_none),
    ] = None
    image: Annotated[
        str | None, BeforeValidator(strip_to_none), AfterValidator(_check_image_url)
    ] = None


class User(FrozenModel):
    id: UUID
    email: str
    name: str | None
    image: str | None
    created_at: datetime


# -------------------------------------------------------------------- sessions
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


# --------------------------------------------------------------------- sign-in
class SignInOutcome(StrEnum):
    """How a sign-in found its user (logged as ``outcome``)."""

    CREATED = "created"
    EXISTING = "existing"
    LINKED = "linked"


class SignedIn(FrozenModel):
    """The user a provider profile signed in as, and how they were found."""

    user: User
    outcome: SignInOutcome
