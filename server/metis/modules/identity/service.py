"""Public API of the identity module: users, workspaces and membership.

Every function takes the caller's ``AsyncSession``, flushes but never commits:
the caller owns the transaction. Each function sets the RLS context it needs
(``app.user_id`` / ``app.workspace_id``) for the current transaction only.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import (
    AlreadyMemberError,
    InvalidInputError,
    MemberUserNotFoundError,
    PermissionDeniedError,
)
from metis.modules.identity import repo
from metis.modules.identity.schemas import (
    MemberRole,
    Membership,
    User,
    UserClaims,
    Workspace,
    WorkspaceName,
)


def _validate[ModelT: BaseModel](model: type[ModelT], **data: Any) -> ModelT:
    """Build ``model`` from ``data`` or raise a 422 ``InvalidInputError``."""
    try:
        return model(**data)
    except ValidationError as exc:
        errors = [
            {"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        raise InvalidInputError("Invalid input", errors=errors) from exc


async def upsert_user_from_claims(
    session: AsyncSession, sub: str, email: str, name: str | None, image: str | None
) -> User:
    claims = _validate(UserClaims, sub=sub, email=email, name=name, image=image)
    row = await repo.upsert_user(session, claims.sub, claims.email, claims.name, claims.image)
    return User.model_validate(row)


async def ensure_personal_workspace(session: AsyncSession, user: User) -> Workspace:
    created_id = await repo.insert_personal_workspace(session, user.id)
    if created_id is not None:
        await repo.set_workspace_context(session, created_id)
        await repo.insert_member(session, created_id, user.id, MemberRole.OWNER)
    return Workspace.model_validate(await repo.get_personal_workspace(session, user.id))


async def list_workspaces(session: AsyncSession, user: User) -> list[Membership]:
    await repo.set_user_context(session, user.id)
    rows = await repo.list_memberships(session, user.id)
    return [
        Membership(workspace=Workspace.model_validate(ws), role=MemberRole(role))
        for ws, role in rows
    ]


async def create_workspace(session: AsyncSession, user: User, name: str) -> Workspace:
    valid = _validate(WorkspaceName, name=name)
    row = await repo.insert_workspace(session, valid.name, user.id)
    await repo.set_workspace_context(session, row.id)
    await repo.insert_member(session, row.id, user.id, MemberRole.OWNER)
    return Workspace.model_validate(row)


async def add_member(
    session: AsyncSession, actor: User, workspace_id: UUID, email: str, role: MemberRole
) -> Membership:
    await repo.set_workspace_context(session, workspace_id)
    # A non-member gets the same error, so it cannot probe which workspaces exist.
    actor_role = await repo.get_member_role(session, workspace_id, actor.id)
    if actor_role != MemberRole.OWNER:
        raise PermissionDeniedError("Only workspace owners can add members")
    user = await repo.get_user_by_email(session, email.strip().lower())
    if user is None:
        raise MemberUserNotFoundError("No user with that email; they must sign in first")
    if not await repo.insert_member(session, workspace_id, user.id, role):
        raise AlreadyMemberError("That user is already a member of this workspace")
    workspace = await repo.get_workspace(session, workspace_id)
    return Membership(workspace=Workspace.model_validate(workspace), role=role)
