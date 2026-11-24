"""Suggestions: ``/v1/ideas/{idea_id}/suggestions`` and ``/v1/suggestions/{suggestion_id}``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from metis.core.db import SessionDep
from metis.modules.identity import CurrentWorkspaceDep
from metis.modules.scoring import service
from metis.modules.scoring.dto import Suggestion, SuggestionList, SuggestionStatusBody

if TYPE_CHECKING:
    from uuid import UUID

idea_router = APIRouter(prefix="/ideas")
router = APIRouter(prefix="/suggestions")


@idea_router.get("/{idea_id}/suggestions", response_model=SuggestionList)
async def list_suggestions(
    session: SessionDep,
    workspace: CurrentWorkspaceDep,
    idea_id: UUID,
    score_run_id: UUID | None = None,
) -> SuggestionList:
    """The idea's suggestions, newest score run first; ``score_run_id`` narrows to one run."""
    return await service.suggestions.list_suggestions(
        session, workspace.workspace.id, idea_id, score_run_id
    )


@router.patch("/{suggestion_id}", response_model=Suggestion)
async def set_suggestion_status(
    session: SessionDep,
    workspace: CurrentWorkspaceDep,
    suggestion_id: UUID,
    body: SuggestionStatusBody,
) -> Suggestion:
    """Mark a suggestion open, accepted or dismissed."""
    return await service.suggestions.set_suggestion_status(
        session, workspace.workspace.id, suggestion_id, body.status
    )
