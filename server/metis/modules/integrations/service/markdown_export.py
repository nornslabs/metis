"""The Markdown file of an idea's spec, score and plan. Read-only: nothing is written."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import NoPlanToExportError, PlanNotFoundError
from metis.core.logging import get_logger
from metis.helpers.dto import FrozenModel
from metis.helpers.slug import title_slug
from metis.modules import ideas, planning, scoring
from metis.modules.integrations.helpers.plan_markdown import PlanExport, render_plan_markdown

log = get_logger(__name__)

FILENAME_SUFFIX = "-plan.md"


class MarkdownFile(FrozenModel):
    """A rendered export and the name to save it under."""

    filename: str
    content: str


async def build_plan_markdown(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID
) -> MarkdownFile:
    """The newest plan for the idea's confirmed spec, as Markdown, with the latest score.

    Unknown or archived idea → ``IdeaNotFoundError``. No confirmed spec or no plan (a draft
    plan counts) → ``NoPlanToExportError``.
    """
    idea = await ideas.get_idea(session, workspace_id, idea_id)
    spec = (await ideas.get_spec_overview(session, workspace_id, idea_id)).confirmed
    if spec is None:
        raise NoPlanToExportError("The idea has no confirmed spec to export")
    try:
        plan = await planning.get_plan(session, workspace_id, idea_id, spec.id)
    except PlanNotFoundError:
        raise NoPlanToExportError("The idea has no plan to export") from None
    score = await scoring.latest_score(session, workspace_id, idea_id)
    content = render_plan_markdown(PlanExport(idea=idea, spec=spec, score=score, plan=plan))
    log.info(
        "markdown_export",
        idea_id=str(idea_id),
        plan_version=plan.version,
        size=len(content.encode()),
    )
    return MarkdownFile(filename=f"{title_slug(idea.title)}{FILENAME_SUFFIX}", content=content)
