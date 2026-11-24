"""An idea's scores: ``/v1/ideas/{idea_id}/scores``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from metis.core.db import SessionDep
from metis.core.errors import ScoreNotFoundError
from metis.modules.identity import CurrentWorkspaceDep
from metis.modules.scoring import service
from metis.modules.scoring.dto import ScoreHistory, ScoreRun

if TYPE_CHECKING:
    from uuid import UUID

router = APIRouter(prefix="/ideas")


@router.get("/{idea_id}/scores", response_model=ScoreHistory)
async def get_score_history(
    session: SessionDep, workspace: CurrentWorkspaceDep, idea_id: UUID
) -> ScoreHistory:
    """The idea's score runs without params, newest first."""
    return await service.scores.score_history(session, workspace.workspace.id, idea_id)


@router.get("/{idea_id}/scores/latest", response_model=ScoreRun)
async def get_latest_score(
    session: SessionDep, workspace: CurrentWorkspaceDep, idea_id: UUID
) -> ScoreRun:
    """The idea's newest score run; 404 ``score.not_found`` before the first one."""
    score = await service.scores.latest_score(session, workspace.workspace.id, idea_id)
    if score is None:
        raise ScoreNotFoundError()
    return score
