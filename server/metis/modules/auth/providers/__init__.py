"""Sign-in providers. Routes get the configured Google provider through ``GoogleProviderDep``.

``get_google_provider`` returns one process-wide ``GoogleProvider`` (its
discovery and JWKS caches stay warm), or ``None`` when Google is not
configured (allowed only in development). Tests override it.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from metis.core.config import get_settings
from metis.helpers.http import make_provider_client
from metis.modules.identity.providers.base import (
    AuthProvider,
    AuthProviderName,
    OAuthFailure,
    OAuthStep,
    ProviderProfile,
    oauth_failed,
)
from metis.modules.identity.providers.google import GoogleProvider


@lru_cache
def _google_from_settings() -> GoogleProvider | None:
    settings = get_settings()
    if (
        settings.google_client_id is None
        or settings.google_client_secret is None
        or settings.google_redirect_uri is None
    ):
        return None
    return GoogleProvider(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret.get_secret_value(),
        redirect_uri=settings.google_redirect_uri,
        client_factory=make_provider_client,
    )


def get_google_provider() -> AuthProvider | None:
    """FastAPI dependency: the Google provider, or ``None`` when not configured."""
    return _google_from_settings()


GoogleProviderDep = Annotated[AuthProvider | None, Depends(get_google_provider)]

__all__ = [
    "AuthProvider",
    "AuthProviderName",
    "GoogleProvider",
    "GoogleProviderDep",
    "OAuthFailure",
    "OAuthStep",
    "ProviderProfile",
    "get_google_provider",
    "oauth_failed",
]
