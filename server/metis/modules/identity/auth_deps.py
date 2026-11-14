"""Cookie-session auth dependency: ``session_user`` (with the CSRF check).

Lives in identity, not ``core``, because it calls ``auth_service`` and ``core``
never imports a module. No route uses it yet: SHIP-267 renames it to
``current_user``, rebuilds ``current_workspace`` on it and drops JWT auth.

Order of checks: missing cookie → ``auth.not_signed_in``; mutation without
``X-Metis-Client: web`` → ``auth.csrf_failed``; then the session must resolve
(``auth.session_expired`` otherwise).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from metis.core.config import get_settings
from metis.core.db import SessionDep
from metis.core.errors import CsrfError, NotSignedInError
from metis.core.logging import bind_context
from metis.core.redis import RedisDep
from metis.modules.identity import auth_service
from metis.modules.identity.schemas import SessionRejection, SessionUser

CLIENT_HEADER = "X-Metis-Client"
WEB_CLIENT = "web"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _check_csrf(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    if request.headers.get(CLIENT_HEADER) != WEB_CLIENT:
        raise auth_service.rejection(
            SessionRejection.CSRF,
            CsrfError(f"Mutations need the {CLIENT_HEADER}: {WEB_CLIENT} header"),
        )


async def session_user(request: Request, session: SessionDep, redis: RedisDep) -> SessionUser:
    """Resolve the request's session cookie to its user, or raise."""
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise auth_service.rejection(SessionRejection.MISSING, NotSignedInError("Not signed in"))
    _check_csrf(request)
    active = await auth_service.resolve_session(session, redis, token)
    caller = await auth_service.get_session_user(session, active)
    bind_context(user_id=str(caller.user.id), session_id=str(caller.session_id))
    return caller


SessionUserDep = Annotated[SessionUser, Depends(session_user)]
