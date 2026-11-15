"""Auth dependencies every protected ``/v1`` route uses: ``current_user`` and ``current_workspace``.

Lives in identity, not ``core``, because it calls ``auth_service`` and ``core``
never imports a module.

``current_user`` resolves the session cookie to its user. Order of checks:
missing cookie → ``auth.not_signed_in``; mutation without
``X-Metis-Client: web`` → ``auth.csrf_failed``; then the session must resolve
(``auth.session_expired`` otherwise). ``check_csrf`` is also used alone by
``/v1/auth/logout``.

``current_workspace`` picks the request's workspace from ``X-Workspace-Id``
(default: personal), checks membership and scopes the request session to it
for RLS. Both share the request session (``SessionDep``).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request

from metis.core.config import get_settings
from metis.core.db import SessionDep, set_user, set_workspace
from metis.core.errors import CsrfError, InvalidInputError, NotSignedInError, PermissionDeniedError
from metis.core.logging import bind_context
from metis.core.redis import RedisDep
from metis.modules.identity import auth_service, service
from metis.modules.identity.schemas import Membership, SessionRejection, SessionUser

CLIENT_HEADER = "X-Metis-Client"
WEB_CLIENT = "web"
WORKSPACE_HEADER = "X-Workspace-Id"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def check_csrf(request: Request) -> None:
    """Refuse a cookie-authenticated mutation without ``X-Metis-Client: web``."""
    if request.method in SAFE_METHODS:
        return
    if request.headers.get(CLIENT_HEADER) != WEB_CLIENT:
        raise auth_service.rejection(
            SessionRejection.CSRF,
            CsrfError(f"Mutations need the {CLIENT_HEADER}: {WEB_CLIENT} header"),
        )


async def current_user(request: Request, session: SessionDep, redis: RedisDep) -> SessionUser:
    """Resolve the request's session cookie to its user, or raise."""
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise auth_service.rejection(SessionRejection.MISSING, NotSignedInError("Not signed in"))
    check_csrf(request)
    active = await auth_service.resolve_session(session, redis, token)
    caller = await auth_service.get_session_user(session, active)
    bind_context(user_id=str(caller.user.id), session_id=str(caller.session_id))
    return caller


CurrentUserDep = Annotated[SessionUser, Depends(current_user)]


def _parse_workspace_id(raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError as exc:
        raise InvalidInputError(
            f"{WORKSPACE_HEADER} must be a UUID",
            errors=[{"field": f"header.{WORKSPACE_HEADER}", "message": "Invalid UUID"}],
        ) from exc


async def current_workspace(
    session: SessionDep,
    caller: CurrentUserDep,
    workspace_id: Annotated[str | None, Header(alias=WORKSPACE_HEADER)] = None,
) -> Membership:
    """Resolve the request's workspace, check membership and scope RLS to it.

    An unknown workspace gets the same 403 as a foreign one, so callers cannot
    probe which workspaces exist.
    """
    target = (
        caller.personal_workspace.id if workspace_id is None else _parse_workspace_id(workspace_id)
    )
    memberships = await service.list_workspaces(session, caller.user)
    membership = next((m for m in memberships if m.workspace.id == target), None)
    if membership is None:
        raise PermissionDeniedError("You are not a member of that workspace")
    await set_user(session, caller.user.id)
    await set_workspace(session, target)
    bind_context(workspace_id=str(target))
    return membership


CurrentWorkspaceDep = Annotated[Membership, Depends(current_workspace)]
