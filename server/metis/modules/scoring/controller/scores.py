"""Score runs by id: ``/v1/scores/{score_run_id}``."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from metis.core.db import SessionDep
from metis.modules.identity import CurrentWorkspaceDep
from metis.modules.scoring import service
from metis.modules.scoring.dto import ScoreRun

router = APIRouter(prefix="/scores")


@router.get("/{score_run_id}", response_model=ScoreRun)
async def get_score_run(
    session: SessionDep, workspace: CurrentWorkspaceDep, score_run_id: UUID
) -> ScoreRun:
    """A score run with its six params."""
    return await service.scores.get_score_run(session, workspace.workspace.id, score_run_id)
