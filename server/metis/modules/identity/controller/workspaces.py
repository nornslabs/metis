"""Workspace routes: ``GET /v1/workspaces/current`` and ``GET`` / ``POST /v1/workspaces``.

Thin controllers: auth comes from the dependencies, work from ``service.workspaces``.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from metis.core.db import SessionDep
from metis.modules.auth import CurrentUserDep
from metis.modules.identity import service
from metis.modules.identity.deps import CurrentWorkspaceDep
from metis.modules.identity.dto import (
    CreateWorkspaceRequest,
    MemberRole,
    Membership,
    MembershipPage,
)

router = APIRouter(prefix="/workspaces")


@router.get("/current", response_model=Membership)
async def get_current_workspace(
    session: SessionDep, caller: CurrentUserDep, workspace: CurrentWorkspaceDep
) -> Membership:
    """The caller's current workspace (``X-Workspace-Id``, default personal) and their role."""
    return await service.workspaces.get_current_workspace(session, caller.user, workspace)


@router.get("", response_model=MembershipPage)
async def list_my_workspaces(session: SessionDep, caller: CurrentUserDep) -> MembershipPage:
    """Every workspace the caller is a member of, with their role."""
    return MembershipPage(items=await service.workspaces.list_workspaces(session, caller.user))


@router.post("", response_model=Membership, status_code=status.HTTP_201_CREATED)
async def create_my_workspace(
    session: SessionDep, caller: CurrentUserDep, body: CreateWorkspaceRequest
) -> Membership:
    """Create a workspace owned by the caller."""
    workspace = await service.workspaces.create_workspace(session, caller.user, body.name)
    return Membership(workspace=workspace, role=MemberRole.OWNER)
