"""The auth dependency every protected ``/v1`` route uses: ``current_user``.

Lives in auth, not ``core``, because it calls ``service`` and ``core`` never
imports a module. Identity builds ``current_workspace`` on top of it.

``current_user`` resolves the session cookie to its user. Order of checks:
missing cookie → ``auth.not_signed_in``; mutation without
``X-Metis-Client: web`` → ``auth.csrf_failed``; then the session must resolve
(``auth.session_expired`` otherwise). ``check_csrf`` is also used alone by
``/v1/auth/logout``. It shares the request session (``SessionDep``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyCookie

from metis.core.config import get_settings
from metis.core.db import SessionDep
from metis.core.errors import CsrfError, NotSignedInError
from metis.core.logging import bind_context
from metis.core.redis import RedisDep
from metis.modules.auth import service
from metis.modules.auth.dto import SessionRejection, SessionUser

CLIENT_HEADER = "X-Metis-Client"
WEB_CLIENT = "web"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_session_cookie_scheme = APIKeyCookie(
    name=get_settings().session_cookie_name,
    scheme_name="SessionCookie",
    description="Session cookie returned by the sign-in flow.",
    auto_error=False,
)


def check_csrf(request: Request) -> None:
    """Refuse a cookie-authenticated mutation without ``X-Metis-Client: web``."""
    if request.method in SAFE_METHODS:
        return
    if request.headers.get(CLIENT_HEADER) != WEB_CLIENT:
        raise service.sessions.rejection(
            SessionRejection.CSRF,
            CsrfError(f"Mutations need the {CLIENT_HEADER}: {WEB_CLIENT} header"),
        )


async def current_user(
    request: Request,
    session: SessionDep,
    redis: RedisDep,
    _cookie: Annotated[str | None, Security(_session_cookie_scheme)] = None,
) -> SessionUser:
    """Resolve the request's session cookie to its user, or raise."""
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise service.sessions.rejection(
            SessionRejection.MISSING, NotSignedInError("Not signed in")
        )
    check_csrf(request)
    active = await service.sessions.resolve_session(session, redis, token)
    caller = await service.sessions.get_session_user(session, active)
    bind_context(user_id=str(caller.user.id), session_id=str(caller.session_id))
    return caller


CurrentUserDep = Annotated[SessionUser, Depends(current_user)]
