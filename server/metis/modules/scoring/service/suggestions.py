"""Suggestions: save the Advisor's improvements, list them and set their status.

Every function takes the caller's ``AsyncSession``, flushes but never commits and is scoped to
the workspace id as well as RLS. A suggestion's text never changes; only ``status`` does.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import IdeaNotFoundError, RunNotFoundError, SuggestionNotFoundError
from metis.core.logging import get_logger
from metis.modules import ideas
from metis.modules.scoring import repo
from metis.modules.scoring.dto import NewSuggestion, Suggestion, SuggestionList, SuggestionStatus
from metis.modules.scoring.models import SuggestionRow

logger = get_logger(__name__)


async def save_suggestion(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    score_run_id: UUID,
    data: NewSuggestion,
) -> Suggestion:
    """Store one suggestion (status ``open``) made from a score run of the idea.

    Unknown or archived idea → ``IdeaNotFoundError``; a score run of another idea (or none)
    → ``RunNotFoundError``.
    """
    await ideas.get_idea(session, workspace_id, idea_id)
    score_run = await repo.score_runs.get(session, workspace_id, score_run_id)
    if score_run is None or score_run.idea_id != idea_id:
        raise RunNotFoundError()
    row = await repo.suggestions.create(
        session,
        workspace_id,
        idea_id,
        score_run_id,
        {
            "kind": data.kind.value,
            "title": data.title,
            "rationale": data.rationale,
            "target_params": [p.value for p in data.target_params],
            "expected_impact": data.expected_impact,
            "evidence": [item.model_dump() for item in data.evidence],
            "status": SuggestionStatus.OPEN.value,
        },
    )
    logger.info("suggestion.saved", suggestion_id=str(row.id), kind=data.kind.value)
    return _view(row)


async def list_suggestions(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    score_run_id: UUID | None = None,
) -> SuggestionList:
    """The idea's suggestions, newest score run first; an unknown idea is not found."""
    await ideas.get_idea(session, workspace_id, idea_id)
    rows = await repo.suggestions.list_for_idea(session, workspace_id, idea_id, score_run_id)
    return SuggestionList(items=tuple(_view(row) for row in rows))


async def set_suggestion_status(
    session: AsyncSession, workspace_id: UUID, suggestion_id: UUID, status: SuggestionStatus
) -> Suggestion:
    """Set the status (any to any); unknown, foreign or archived → ``SuggestionNotFoundError``."""
    row = await repo.suggestions.get(session, workspace_id, suggestion_id)
    if row is None:
        raise SuggestionNotFoundError()
    try:
        await ideas.get_idea(session, workspace_id, row.idea_id)
    except IdeaNotFoundError:
        raise SuggestionNotFoundError() from None
    updated = await repo.suggestions.set_status(session, workspace_id, suggestion_id, status.value)
    if updated is None:  # gone meanwhile
        raise SuggestionNotFoundError()
    return _view(updated)


def _view(row: SuggestionRow) -> Suggestion:
    return Suggestion.model_validate(row)
