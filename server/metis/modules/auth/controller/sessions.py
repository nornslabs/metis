"""Session routes: ``GET /v1/auth/me``, ``POST /v1/auth/logout`` and ``/logout-all``.

``/me`` authenticates the session cookie and returns its user. Both sign-out routes follow the
cookie CSRF rule (``X-Metis-Client: web``) and clear the session cookie.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from metis.core.config import get_settings
from metis.core.db import SessionDep
from metis.core.redis import RedisDep
from metis.core.security import clear_session_cookie
from metis.modules.auth import service
from metis.modules.auth.deps import CurrentUserDep, check_csrf
from metis.modules.auth.dto import User

router = APIRouter()


@router.get("/me", response_model=User)
async def me(caller: CurrentUserDep) -> User:
    """The user the session cookie belongs to; 401 if there is no valid session."""
    return caller.user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout(request: Request, session: SessionDep, redis: RedisDep) -> Response:
    """End this browser's session (if any) and clear the cookie."""
    check_csrf(request)
    token = request.cookies.get(get_settings().session_cookie_name)
    if token:
        await service.sessions.logout(session, redis, token)
    return _no_content()


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout_all(caller: CurrentUserDep, session: SessionDep, redis: RedisDep) -> Response:
    """End every session of the signed-in user and clear this browser's cookie."""
    await service.sessions.logout_all(session, redis, caller.user.id)
    return _no_content()


def _no_content() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    return response
