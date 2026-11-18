"""An idea's research: ``/v1/ideas/{idea_id}/research``."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from metis.core.db import SessionDep
from metis.core.errors import ResearchNotFoundError
from metis.modules.identity import CurrentWorkspaceDep
from metis.modules.research import service
from metis.modules.research.dto import ResearchView

router = APIRouter(prefix="/ideas")


@router.get("/{idea_id}/research", response_model=ResearchView)
async def get_latest_research(
    session: SessionDep, workspace: CurrentWorkspaceDep, idea_id: UUID
) -> ResearchView:
    """The idea's latest closed research snapshot; 404 ``research.not_found`` before one exists."""
    view = await service.snapshots.latest_snapshot(session, workspace.workspace.id, idea_id)
    if view is None:
        raise ResearchNotFoundError()
    return view
