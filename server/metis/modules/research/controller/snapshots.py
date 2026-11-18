"""Research snapshots by id: ``/v1/research/snapshots/{snapshot_id}``."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from metis.core.db import SessionDep
from metis.modules.identity import CurrentWorkspaceDep
from metis.modules.research import service
from metis.modules.research.dto import ResearchView

router = APIRouter(prefix="/research/snapshots")


@router.get("/{snapshot_id}", response_model=ResearchView)
async def get_snapshot(
    session: SessionDep, workspace: CurrentWorkspaceDep, snapshot_id: UUID
) -> ResearchView:
    """A research snapshot, open or closed, with its items and competitors."""
    return await service.snapshots.get_snapshot(session, workspace.workspace.id, snapshot_id)
