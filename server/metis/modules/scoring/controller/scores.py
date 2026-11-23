"""Score runs: ``/v1/scores/summaries`` and ``/v1/scores/{score_run_id}``."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from metis.core.db import SessionDep
from metis.core.errors import InvalidInputError
from metis.modules.identity import CurrentWorkspaceDep
from metis.modules.scoring import service
from metis.modules.scoring.dto import IdeaScoreSummaryList, ScoreRun

router = APIRouter(prefix="/scores")

MAX_SUMMARY_IDS = 50


@router.get("/summaries", response_model=IdeaScoreSummaryList)
async def get_score_summaries(
    session: SessionDep,
    workspace: CurrentWorkspaceDep,
    idea_ids: Annotated[str, Query(description="Comma-separated idea ids, 1 to 50")],
) -> IdeaScoreSummaryList:
    """Score totals per version (oldest first) and the latest band, for several ideas at once."""
    ids = _parse_idea_ids(idea_ids)
    return await service.scores.score_summaries(session, workspace.workspace.id, ids)


@router.get("/{score_run_id}", response_model=ScoreRun)
async def get_score_run(
    session: SessionDep, workspace: CurrentWorkspaceDep, score_run_id: UUID
) -> ScoreRun:
    """A score run with its six params."""
    return await service.scores.get_score_run(session, workspace.workspace.id, score_run_id)


def _parse_idea_ids(raw: str) -> list[UUID]:
    """1 to ``MAX_SUMMARY_IDS`` distinct uuids; anything else is a 422."""
    try:
        ids = list(dict.fromkeys(UUID(part.strip()) for part in raw.split(",")))
    except ValueError as exc:
        raise InvalidInputError(
            "Invalid idea id", errors=[{"field": "query.idea_ids", "message": "Invalid idea id"}]
        ) from exc
    if not 1 <= len(ids) <= MAX_SUMMARY_IDS:
        message = f"Give 1 to {MAX_SUMMARY_IDS} idea ids"
        raise InvalidInputError(message, errors=[{"field": "query.idea_ids", "message": message}])
    return ids
