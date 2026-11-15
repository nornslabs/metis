"""Workspace DTOs: names, workspaces, memberships and the workspace-list body."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BeforeValidator, Field

from metis.helpers.dto import FrozenModel
from metis.helpers.text import strip
from metis.modules.identity.dto.members import MemberRole

MAX_WORKSPACE_NAME_LENGTH = 100


class WorkspaceName(FrozenModel):
    name: Annotated[
        str, BeforeValidator(strip), Field(min_length=1, max_length=MAX_WORKSPACE_NAME_LENGTH)
    ]


class Workspace(FrozenModel):
    id: UUID
    name: str
    is_personal: bool
    created_by: UUID
    created_at: datetime


class Membership(FrozenModel):
    workspace: Workspace
    role: MemberRole


class CreateWorkspaceRequest(FrozenModel):
    """Body of ``POST /v1/workspaces``; the service validates and trims ``name``."""

    name: str


class MembershipPage(FrozenModel):
    items: list[Membership]
    next_cursor: str | None = None
