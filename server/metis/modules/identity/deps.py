"""The workspace dependency every workspace-scoped ``/v1`` route uses: ``current_workspace``.

Built on ``auth.CurrentUserDep``. It picks the request's workspace from
``X-Workspace-Id`` (default: personal), checks membership and scopes the
request session to it for RLS. The personal workspace is created here on the
user's first workspace-scoped call by ``service.workspaces.ensure_personal_workspace``,
the one rule ``/v1/workspaces/current`` shares (idempotent, same transaction).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Query

from metis.core.db import SessionDep, set_user, set_workspace
from metis.core.errors import InvalidInputError, PermissionDeniedError
from metis.core.logging import bind_context
from metis.modules.auth import CurrentUserDep, SessionUser
from metis.modules.identity import service
from metis.modules.identity.dto import Membership

WORKSPACE_HEADER = "X-Workspace-Id"


async def current_workspace(
    session: SessionDep,
    caller: CurrentUserDep,
    workspace_id: Annotated[str | None, Header(alias=WORKSPACE_HEADER)] = None,
) -> Membership:
    """Resolve the request's workspace, check membership and scope RLS to it.

    An unknown workspace gets the same 403 as a foreign one, so callers cannot
    probe which workspaces exist.
    """
    return await _scope_to_workspace(session, caller, workspace_id)


async def stream_workspace(
    session: SessionDep,
    caller: CurrentUserDep,
    header_id: Annotated[str | None, Header(alias=WORKSPACE_HEADER)] = None,
    query_id: Annotated[str | None, Query(alias="workspace_id")] = None,
) -> Membership:
    """``current_workspace`` for ``EventSource`` routes, which cannot set headers.

    Also reads ``?workspace_id=``; the header wins when both are sent.
    """
    return await _scope_to_workspace(session, caller, header_id or query_id)


async def _scope_to_workspace(
    session: SessionDep, caller: SessionUser, raw_workspace_id: str | None
) -> Membership:
    if raw_workspace_id is None:
        target = (await service.workspaces.ensure_personal_workspace(session, caller.user)).id
    else:
        target = _parse_workspace_id(raw_workspace_id)
    memberships = await service.workspaces.list_workspaces(session, caller.user)
    membership = next((m for m in memberships if m.workspace.id == target), None)
    if membership is None:
        raise PermissionDeniedError("You are not a member of that workspace")
    await set_user(session, caller.user.id)
    await set_workspace(session, target)
    bind_context(workspace_id=str(target))
    return membership


CurrentWorkspaceDep = Annotated[Membership, Depends(current_workspace)]
StreamWorkspaceDep = Annotated[Membership, Depends(stream_workspace)]


def _parse_workspace_id(raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError as exc:
        raise InvalidInputError(
            f"{WORKSPACE_HEADER} must be a UUID",
            errors=[{"field": f"header.{WORKSPACE_HEADER}", "message": "Invalid UUID"}],
        ) from exc
