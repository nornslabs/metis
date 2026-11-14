"""Bearer-token verification for the API.

The web app mints an HS256-signed JWT with ``AUTH_JWT_SECRET`` and
``AUTH_JWT_AUDIENCE``; the API verifies it here. This is the only module that
imports the JWT library. Turning claims into a user and a workspace lives in
the identity module (``current_user`` / ``current_workspace``).

Never log the token, the ``Authorization`` header or the secret.
"""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from metis.core.config import get_settings
from metis.core.errors import AuthError, TokenExpiredError
from metis.core.logging import get_logger

JWT_ALGORITHM = "HS256"
CLOCK_SKEW_SECONDS = 30
_REQUIRED_CLAIMS = ["exp", "aud", "sub"]

logger = get_logger(__name__)

# auto_error=False: a missing or non-Bearer header becomes our RFC 7807 401,
# not FastAPI's default error body. Also documents the scheme in OpenAPI.
bearer_scheme = HTTPBearer(auto_error=False)


class TokenClaims(BaseModel):
    """The claims Metis uses from a verified token (Auth.js names)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    sub: Annotated[str, Field(min_length=1)]
    email: Annotated[str, Field(min_length=1)]
    name: str | None = None
    picture: str | None = None


def _reject(reason: str, error: AuthError) -> AuthError:
    logger.info("auth.rejected", reason=reason)
    return error


def verify_token(token: str) -> TokenClaims:
    """Verify an HS256 JWT (signature, ``aud``, ``exp`` with leeway) and return its claims.

    Raises ``TokenExpiredError`` when expired, ``AuthError`` for anything else.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[JWT_ALGORITHM],
            audience=settings.auth_jwt_audience,
            leeway=CLOCK_SKEW_SECONDS,
            options={"require": _REQUIRED_CLAIMS},
        )
    except jwt.ExpiredSignatureError as exc:
        raise _reject("expired", TokenExpiredError("Token has expired")) from exc
    except jwt.InvalidTokenError as exc:
        raise _reject("invalid", AuthError("Invalid token")) from exc
    try:
        return TokenClaims.model_validate(payload)
    except ValidationError as exc:
        raise _reject("claims", AuthError("Token is missing required claims")) from exc


def bearer_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> TokenClaims:
    """FastAPI dependency: the verified claims of the request's bearer token."""
    if credentials is None:
        raise _reject("missing", AuthError("Missing bearer token"))
    return verify_token(credentials.credentials)


__all__ = [
    "CLOCK_SKEW_SECONDS",
    "JWT_ALGORITHM",
    "TokenClaims",
    "bearer_claims",
    "bearer_scheme",
    "verify_token",
]
