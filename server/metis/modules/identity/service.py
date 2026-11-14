"""Public API of the identity module: users, workspaces and membership.

Every function takes the caller's ``AsyncSession``, flushes but never commits:
the caller owns the transaction. Each function sets the RLS context it needs
(``app.user_id`` / ``app.workspace_id``) and restores the caller's value after.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.db import USER_SETTING, WORKSPACE_SETTING
from metis.core.errors import (
    AlreadyMemberError,
    EmailTakenError,
    InvalidInputError,
    MemberUserNotFoundError,
    PermissionDeniedError,
    WorkspaceNotFoundError,
)
from metis.modules.identity import repo
from metis.modules.identity.schemas import (
    MemberRole,
    Membership,
    NewMember,
    User,
    UserClaims,
    Workspace,
    WorkspaceName,
)

PERSONAL_WORKSPACE_NAME = "Personal"


def _validate[ModelT: BaseModel](model: type[ModelT], **data: object) -> ModelT:
    """Build ``model`` from ``data`` or raise a 422 ``InvalidInputError``."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        errors = [
            {"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        raise InvalidInputError("Invalid input", errors=errors) from exc


async def _add_owner(session: AsyncSession, workspace_id: UUID, user_id: UUID) -> None:
    async with repo.rls_context(session, WORKSPACE_SETTING, workspace_id):
        await repo.insert_member(session, workspace_id, user_id, MemberRole.OWNER)


async def upsert_user_from_claims(
    session: AsyncSession, sub: str, email: str, name: str | None, image: str | None
) -> User:
    claims = _validate(UserClaims, sub=sub, email=email, name=name, image=image)
    row = await repo.upsert_user(session, claims)
    if row is None:
        raise EmailTakenError("That email already belongs to another account")
    return User.model_validate(row)


async def ensure_personal_workspace(session: AsyncSession, user: User) -> Workspace:
    created = await repo.insert_workspace(
        session, PERSONAL_WORKSPACE_NAME, user.id, is_personal=True
    )
    if created is not None:
        await _add_owner(session, created.id, user.id)
        return Workspace.model_validate(created)
    return Workspace.model_validate(await repo.get_personal_workspace(session, user.id))


async def list_workspaces(session: AsyncSession, user: User) -> list[Membership]:
    async with repo.rls_context(session, USER_SETTING, user.id):
        rows = await repo.list_memberships(session, user.id)
    return [Membership(workspace=Workspace.model_validate(ws), role=role) for ws, role in rows]


async def create_workspace(session: AsyncSession, user: User, name: str) -> Workspace:
    valid = _validate(WorkspaceName, name=name)
    row = await repo.insert_workspace(session, valid.name, user.id, is_personal=False)
    if row is None:  # unreachable: only a personal insert can be skipped
        raise WorkspaceNotFoundError("Workspace was not created")
    await _add_owner(session, row.id, user.id)
    return Workspace.model_validate(row)


async def add_member(
    session: AsyncSession, actor: User, workspace_id: UUID, email: str, role: MemberRole
) -> Membership:
    new = _validate(NewMember, email=email, role=role)
    async with repo.rls_context(session, WORKSPACE_SETTING, workspace_id):
        # A non-member gets the same error, so it cannot probe which workspaces exist.
        if await repo.get_member_role(session, workspace_id, actor.id) != MemberRole.OWNER:
            raise PermissionDeniedError("Only workspace owners can add members")
        user = await repo.get_user_by_email(session, new.email)
        if user is None:
            raise MemberUserNotFoundError("No user with that email; they must sign in first")
        if not await repo.insert_member(session, workspace_id, user.id, new.role):
            raise AlreadyMemberError("That user is already a member of this workspace")
    workspace = await repo.get_workspace(session, workspace_id)
    if workspace is None:
        raise WorkspaceNotFoundError()
    return Membership(workspace=Workspace.model_validate(workspace), role=new.role)
