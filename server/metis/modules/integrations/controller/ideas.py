"""An idea's exports: ``GET /v1/ideas/{idea_id}/export.md``.

Any workspace member may download it. It reads and renders; it writes nothing and calls no
outside service, so it needs no approval.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response

from metis.core.db import SessionDep
from metis.modules.identity import CurrentWorkspaceDep
from metis.modules.integrations import service

router = APIRouter(prefix="/ideas")

MARKDOWN_MEDIA_TYPE = "text/markdown; charset=utf-8"


@router.get(
    "/{idea_id}/export.md",
    response_class=Response,
    responses={200: {"content": {"text/markdown": {}}}},
)
async def export_markdown(
    session: SessionDep, workspace: CurrentWorkspaceDep, idea_id: UUID
) -> Response:
    """The confirmed spec, latest score and plan as one Markdown file to save."""
    file = await service.markdown_export.build_plan_markdown(
        session, workspace.workspace.id, idea_id
    )
    return Response(
        content=file.content,
        media_type=MARKDOWN_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{file.filename}"'},
    )
