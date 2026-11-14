"""Session tokens and the session cookie.

A session token is 32 random bytes (URL-safe base64). Only its SHA-256 hash is
stored; the raw token lives in the browser's ``HttpOnly`` cookie and is never
logged. Resolving tokens to sessions lives in the identity module
(``auth_service``).
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Final

from starlette.responses import Response

from metis.core.config import get_settings

SESSION_TOKEN_BYTES = 32
SECONDS_PER_DAY = 86_400
COOKIE_PATH = "/"
COOKIE_SAMESITE: Final = "lax"


def new_session_token() -> str:
    """Return a fresh random session token (URL-safe, 32 bytes of entropy)."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> bytes:
    """Return the SHA-256 digest stored for ``token``."""
    return hashlib.sha256(token.encode("utf-8")).digest()


def set_session_cookie(response: Response, token: str) -> None:
    """Set the ``HttpOnly`` session cookie on ``response`` for ``SESSION_TTL_DAYS``."""
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_days * SECONDS_PER_DAY,
        path=COOKIE_PATH,
        domain=settings.cookie_domain,
        secure=settings.secure_cookies,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )


def clear_session_cookie(response: Response) -> None:
    """Delete the session cookie (same name, path and domain it was set with)."""
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path=COOKIE_PATH,
        domain=settings.cookie_domain,
        secure=settings.secure_cookies,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )


__all__ = [
    "SESSION_TOKEN_BYTES",
    "clear_session_cookie",
    "hash_session_token",
    "new_session_token",
    "set_session_cookie",
]
