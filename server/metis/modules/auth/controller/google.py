"""Google sign-in routes: ``GET /v1/auth/google/login`` and ``/callback``.

Login and callback answer with browser redirects, never JSON errors: a failed callback goes to
``{WEB_BASE_URL}/sign-in?error=<code>`` with no cookie (``finish_login`` rolls its writes back).
Thin controllers: the work lives in ``service.oauth``.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import RedirectResponse

from metis.core.config import get_settings
from metis.core.db import SessionDep
from metis.core.errors import MetisError
from metis.core.redis import RedisDep
from metis.core.security import set_session_cookie
from metis.modules.auth import service
from metis.modules.auth.providers import GoogleProviderDep
from metis.modules.auth.providers.base import (
    AuthProvider,
    AuthProviderName,
    OAuthFailure,
    OAuthStep,
    oauth_failed,
)

router = APIRouter(prefix="/google")


OptionalQuery = Annotated[str | None, Query()]


@router.get("/login", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def google_login(
    redis: RedisDep, google: GoogleProviderDep, redirect_to: OptionalQuery = None
) -> RedirectResponse:
    """Send the browser to Google; ``redirect_to`` is where to land after sign-in."""
    try:
        provider = _require(google, AuthProviderName.GOOGLE, OAuthStep.LOGIN)
        return _redirect(await service.oauth.start_login(redis, provider, redirect_to))
    except MetisError as exc:
        return _sign_in_error(exc)


@router.get("/callback", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
async def google_callback(
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    google: GoogleProviderDep,
    code: OptionalQuery = None,
    state: OptionalQuery = None,
    error: OptionalQuery = None,
) -> RedirectResponse:
    """Finish the Google sign-in, set the session cookie and return to the web app."""
    try:
        provider = _require(google, AuthProviderName.GOOGLE, OAuthStep.CALLBACK)
        finished = await service.oauth.finish_login(
            session,
            redis,
            provider,
            code=code,
            state=state,
            error=error,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
    except MetisError as exc:
        return _sign_in_error(exc)
    response = _redirect(_web_url(finished.redirect_to))
    set_session_cookie(response, finished.token)
    return response


def _web_url(path: str) -> str:
    return get_settings().web_base_url.rstrip("/") + path


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


def _sign_in_error(exc: MetisError) -> RedirectResponse:
    return _redirect(_web_url("/sign-in?" + urlencode({"error": exc.code.value})))


def _require(
    provider: AuthProvider | None, name: AuthProviderName, step: OAuthStep
) -> AuthProvider:
    if provider is None:
        raise oauth_failed(name, step, OAuthFailure.NOT_CONFIGURED)
    return provider
