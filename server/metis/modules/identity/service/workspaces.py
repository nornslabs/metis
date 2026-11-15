"""Workspaces and the caller's memberships. Users come from ``metis.modules.auth``.

Every function takes the caller's ``AsyncSession``, flushes but never commits: the caller
owns the transaction. Each function sets the RLS context it needs (``app.user_id`` /
``app.workspace_id``) and restores the caller's value after.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.db import USER_SETTING, WORKSPACE_SETTING
from metis.core.errors import WorkspaceNotFoundError
from metis.helpers.validation import validate_input
from metis.modules import auth
from metis.modules.identity import repo
from metis.modules.identity.dto import MemberRole, Membership, Workspace, WorkspaceName

PERSONAL_WORKSPACE_NAME = "Personal"


async def ensure_personal_workspace(
    session: AsyncSession, user: auth.User, current: Workspace | None = None
) -> Workspace:
    """The user's personal workspace, created on first use (idempotent, race-safe).

    The single rule for creating it: ``current_workspace`` and ``/v1/workspaces/current`` both
    call this. ``current`` is the request's workspace when already resolved; if
    it is the user's personal one, it is returned without touching the DB.
    """
    if current is not None and current.is_personal and current.created_by == user.id:
        return current
    created = await repo.workspaces.create(
        session, PERSONAL_WORKSPACE_NAME, user.id, is_personal=True
    )
    if created is not None:
        await _add_owner(session, created.id, user.id)
        return Workspace.model_validate(created)
    return Workspace.model_validate(await repo.workspaces.get_personal(session, user.id))


async def list_workspaces(session: AsyncSession, user: auth.User) -> list[Membership]:
    async with repo.rls.context(session, USER_SETTING, user.id):
        rows = await repo.members.list_for_user(session, user.id)
    return [Membership(workspace=Workspace.model_validate(ws), role=role) for ws, role in rows]


async def get_current_workspace(
    session: AsyncSession, user: auth.User, current: Membership
) -> Membership:
    """The caller's current workspace; makes sure the personal workspace exists first.

    The first call always creates it, even when it is sent with an
    ``X-Workspace-Id`` (without one, ``current_workspace`` already did).
    """
    await ensure_personal_workspace(session, user, current.workspace)
    return current


async def create_workspace(session: AsyncSession, user: auth.User, name: str) -> Workspace:
    valid = validate_input(WorkspaceName, name=name)
    row = await repo.workspaces.create(session, valid.name, user.id, is_personal=False)
    if row is None:  # unreachable: only a personal insert can be skipped
        raise WorkspaceNotFoundError("Workspace was not created")
    await _add_owner(session, row.id, user.id)
    return Workspace.model_validate(row)


async def _add_owner(session: AsyncSession, workspace_id: UUID, user_id: UUID) -> None:
    async with repo.rls.context(session, WORKSPACE_SETTING, workspace_id):
        await repo.members.create(session, workspace_id, user_id, MemberRole.OWNER)
