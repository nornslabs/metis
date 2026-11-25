"""Export results: ``GET /v1/exports/summaries``.

Any workspace member may read it. It reads what the exports saved and calls no outside service.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from metis.core.db import SessionDep
from metis.core.errors import InvalidInputError
from metis.modules.identity import CurrentWorkspaceDep
from metis.modules.integrations import service
from metis.modules.integrations.dto import ExportSummaryList

router = APIRouter(prefix="/exports")

MAX_SUMMARY_IDS = 50


@router.get("/summaries", response_model=ExportSummaryList)
async def get_export_summaries(
    session: SessionDep,
    workspace: CurrentWorkspaceDep,
    idea_ids: Annotated[str, Query(description="Comma-separated idea ids, 1 to 50")],
) -> ExportSummaryList:
    """The newest finished export of each idea: status, Linear project URL, counts, failures."""
    ids = _parse_idea_ids(idea_ids)
    return await service.exports.export_summaries(session, workspace.workspace.id, ids)


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
