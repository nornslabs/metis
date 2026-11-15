"""The sign-in provider contract: send the browser away, then turn the answer into a profile.

Every provider (Google now, email later) implements ``AuthProvider``. The
OAuth round trip (``service.start_login`` / ``finish_login``) and
``service.sign_in`` only see this protocol and ``ProviderProfile``, so
adding a provider changes neither.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from metis.core.errors import OAuthFailedError
from metis.core.logging import get_logger

logger = get_logger(__name__)


class AuthProviderName(StrEnum):
    """Sign-in methods; matches the ``auth.identities.provider`` CHECK."""

    GOOGLE = "google"
    EMAIL = "email"


class OAuthStep(StrEnum):
    """Where in the sign-in a failure happened (logged as ``step``)."""

    LOGIN = "login"
    CALLBACK = "callback"
    DISCOVERY = "discovery"
    TOKEN = "token"
    JWKS = "jwks"
    ID_TOKEN = "id_token"
    SIGN_IN = "sign_in"


class OAuthFailure(StrEnum):
    """Why a sign-in failed (logged as ``reason`` with ``auth.oauth_failed``)."""

    NOT_CONFIGURED = "not_configured"
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    STATE_STORE_UNAVAILABLE = "state_store_unavailable"
    PROVIDER_ERROR = "provider_error"
    MISSING_CODE = "missing_code"
    BAD_RESPONSE = "bad_response"
    UNKNOWN_KEY = "unknown_key"
    ID_TOKEN_INVALID = "id_token_invalid"
    NONCE_MISMATCH = "nonce_mismatch"
    SIGN_IN_CONFLICT = "sign_in_conflict"


def oauth_failed(
    provider: AuthProviderName, step: OAuthStep, reason: OAuthFailure
) -> OAuthFailedError:
    """Log a failed sign-in step (never secrets) and return the error to raise."""
    logger.warning(
        "auth.oauth_failed", provider=provider.value, step=step.value, reason=reason.value
    )
    return OAuthFailedError("Sign-in with the provider failed", meta={"reason": reason.value})


class ProviderProfile(BaseModel):
    """Who the provider vouches for, after its answer was verified."""

    model_config = ConfigDict(frozen=True)

    provider: AuthProviderName
    subject: str
    email: str
    email_verified: bool
    name: str | None = None
    avatar_url: str | None = None


class AuthProvider(Protocol):
    """A sign-in provider reached through a browser redirect."""

    @property
    def name(self) -> AuthProviderName: ...

    async def authorization_url(self, state: str, nonce: str, code_challenge: str) -> str:
        """Where to send the browser to sign in."""
        ...

    async def complete(self, code: str, code_verifier: str, nonce: str) -> ProviderProfile:
        """Exchange ``code`` and verify the answer; raise ``OAuthFailedError`` otherwise."""
        ...
