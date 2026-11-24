"""Adding members to a workspace (owners only).

Every function takes the caller's ``AsyncSession``, flushes but never commits: the caller
owns the transaction. Each function sets the RLS context it needs (``app.user_id`` /
``app.workspace_id``) and restores the caller's value after.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.db import WORKSPACE_SETTING
from metis.core.errors import (
    AlreadyMemberError,
    MemberUserNotFoundError,
    PermissionDeniedError,
    WorkspaceNotFoundError,
)
from metis.helpers.validation import validate_input
from metis.modules import auth
from metis.modules.identity import repo
from metis.modules.identity.dto import MemberRole, Membership, NewMember, Workspace

if TYPE_CHECKING:
    from uuid import UUID


async def add_member(
    session: AsyncSession, actor: auth.User, workspace_id: UUID, email: str, role: MemberRole
) -> Membership:
    new = validate_input(NewMember, email=email, role=role)
    async with repo.rls.context(session, WORKSPACE_SETTING, workspace_id):
        # A non-member gets the same error, so it cannot probe which workspaces exist.
        if await repo.members.get_role(session, workspace_id, actor.id) != MemberRole.OWNER:
            raise PermissionDeniedError("Only workspace owners can add members")
        user = await auth.find_user_by_email(session, new.email)
        if user is None:
            raise MemberUserNotFoundError("No user with that email; they must sign in first")
        if not await repo.members.create(session, workspace_id, user.id, new.role):
            raise AlreadyMemberError("That user is already a member of this workspace")
    workspace = await repo.workspaces.get(session, workspace_id)
    if workspace is None:
        raise WorkspaceNotFoundError()
    return Membership(workspace=Workspace.model_validate(workspace), role=new.role)
