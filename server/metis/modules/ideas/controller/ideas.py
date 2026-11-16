"""Idea routes: ``/v1/ideas``.

Thin controllers: auth and workspace scope come from the dependencies, work from
``service.ideas``. Bodies are the validated DTOs, so bad input is a 422.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from metis.core.db import SessionDep
from metis.modules.auth import CurrentUserDep
from metis.modules.ideas import service
from metis.modules.ideas.dto import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    Idea,
    IdeaPage,
    IdeaPatch,
    NewIdea,
)
from metis.modules.identity import CurrentWorkspaceDep

router = APIRouter(prefix="/ideas")


@router.post("", response_model=Idea, status_code=status.HTTP_201_CREATED)
async def create_idea(
    session: SessionDep, caller: CurrentUserDep, workspace: CurrentWorkspaceDep, body: NewIdea
) -> Idea:
    """Submit an idea; it starts at stage ``intake``."""
    return await service.ideas.create_idea(session, caller.user, workspace, body)


@router.get("", response_model=IdeaPage)
async def list_ideas(
    session: SessionDep,
    workspace: CurrentWorkspaceDep,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> IdeaPage:
    """The workspace's ideas, newest first; pass ``next_cursor`` as ``cursor`` for the next page."""
    return await service.ideas.list_ideas(session, workspace.workspace.id, cursor, limit)


@router.get("/{idea_id}", response_model=Idea)
async def get_idea(session: SessionDep, workspace: CurrentWorkspaceDep, idea_id: UUID) -> Idea:
    return await service.ideas.get_idea(session, workspace.workspace.id, idea_id)


@router.patch("/{idea_id}", response_model=Idea)
async def update_idea(
    session: SessionDep,
    caller: CurrentUserDep,
    workspace: CurrentWorkspaceDep,
    idea_id: UUID,
    body: IdeaPatch,
) -> Idea:
    """Edit an idea; ``version`` must match the one read (409 otherwise)."""
    return await service.ideas.update_idea(session, caller.user, workspace, idea_id, body)


@router.delete("/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_idea(
    session: SessionDep, caller: CurrentUserDep, workspace: CurrentWorkspaceDep, idea_id: UUID
) -> Response:
    """Archive an idea (soft delete)."""
    await service.ideas.archive_idea(session, caller.user, workspace, idea_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
