"""Auth dependencies every ``/v1`` route uses: ``current_user`` and ``current_workspace``.

``current_user`` turns verified token claims into an identity user with a
personal workspace. ``current_workspace`` picks the request's workspace from
``X-Workspace-Id`` (default: personal), checks membership and scopes the
request session to it for RLS. Both share the request session (``SessionDep``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header

from metis.core.auth import TokenClaims, bearer_claims
from metis.core.db import SessionDep, set_user, set_workspace
from metis.core.errors import AuthError, InvalidInputError, PermissionDeniedError
from metis.core.logging import bind_context
from metis.modules.identity import service
from metis.modules.identity.schemas import Membership, User, Workspace

WORKSPACE_HEADER = "X-Workspace-Id"


@dataclass(frozen=True)
class CurrentUser:
    """The signed-in user and their personal workspace."""

    user: User
    personal_workspace: Workspace


async def current_user(
    session: SessionDep, claims: Annotated[TokenClaims, Depends(bearer_claims)]
) -> CurrentUser:
    """Verify the token, then upsert the user and ensure their personal workspace."""
    try:
        user = await service.upsert_user_from_claims(
            session, claims.sub, claims.email, claims.name, claims.picture
        )
    except InvalidInputError as exc:
        raise AuthError("Token claims are invalid") from exc
    personal = await service.ensure_personal_workspace(session, user)
    bind_context(user_id=str(user.id))
    return CurrentUser(user=user, personal_workspace=personal)


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
    caller: Annotated[CurrentUser, Depends(current_user)],
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


CurrentUserDep = Annotated[CurrentUser, Depends(current_user)]
CurrentWorkspaceDep = Annotated[Membership, Depends(current_workspace)]
