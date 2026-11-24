"""Auth DTOs (validated inputs, records, results), one file per domain."""

from __future__ import annotations

from metis.modules.auth.dto.oauth import FinishedLogin, PendingLogin
from metis.modules.auth.dto.sessions import (
    ActiveSession,
    CacheLookup,
    NewSession,
    SessionRecord,
    SessionRejection,
    SessionUser,
)
from metis.modules.auth.dto.sign_in import SignedIn, SignInOutcome
from metis.modules.auth.dto.users import IMAGE_URL_SCHEMES, MAX_NAME_LENGTH, User, UserClaims

__all__ = [
    "IMAGE_URL_SCHEMES",
    "MAX_NAME_LENGTH",
    "ActiveSession",
    "CacheLookup",
    "FinishedLogin",
    "NewSession",
    "PendingLogin",
    "SessionRecord",
    "SessionRejection",
    "SessionUser",
    "SignInOutcome",
    "SignedIn",
    "User",
    "UserClaims",
]
