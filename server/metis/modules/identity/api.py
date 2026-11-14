"""HTTP routes of the identity module: ``/v1/me`` and ``/v1/workspaces``.

Thin controllers: auth comes from the dependencies, work from ``service.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from metis.core.db import SessionDep
from metis.modules.identity import service
from metis.modules.identity.deps import CurrentUserDep, CurrentWorkspaceDep
from metis.modules.identity.schemas import (
    CreateWorkspaceRequest,
    MemberRole,
    Membership,
    MembershipPage,
    MeResponse,
)

router = APIRouter(prefix="/v1", tags=["identity"])


@router.get("/me", response_model=MeResponse)
async def get_me(
    session: SessionDep, caller: CurrentUserDep, workspace: CurrentWorkspaceDep
) -> MeResponse:
    """The signed-in user, their workspaces and the request's current workspace."""
    memberships = await service.list_workspaces(session, caller.user)
    return MeResponse(user=caller.user, workspaces=memberships, current_workspace=workspace)


@router.get("/workspaces", response_model=MembershipPage)
async def list_my_workspaces(session: SessionDep, caller: CurrentUserDep) -> MembershipPage:
    """Every workspace the caller is a member of, with their role."""
    return MembershipPage(items=await service.list_workspaces(session, caller.user))


@router.post("/workspaces", response_model=Membership, status_code=status.HTTP_201_CREATED)
async def create_my_workspace(
    session: SessionDep, caller: CurrentUserDep, body: CreateWorkspaceRequest
) -> Membership:
    """Create a workspace owned by the caller."""
    workspace = await service.create_workspace(session, caller.user, body.name)
    return Membership(workspace=workspace, role=MemberRole.OWNER)


__all__ = ["router"]
