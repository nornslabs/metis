"""What the Scorer and the Advisor both start from: the idea, its interview and the research.

``idea_seed_parts`` also fills a ``SourceBook`` with the research's own URLs, so a specialist
can check that the sources a model cites are ones the run really saw.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from metis.agent.tools.research_kb import ResearchScope
from metis.agent.tools.scoring import SourceBook
from metis.modules import ideas, research


async def idea_seed_parts(
    session: AsyncSession, scope: ResearchScope, book: SourceBook
) -> list[str]:
    """The idea's text, the interview brief, the user's answers and the latest research."""
    idea = await ideas.get_idea(session, scope.workspace_id, scope.idea_id)
    brief = await ideas.get_interview_brief(session, scope.workspace_id, scope.idea_id)
    turns = await ideas.list_turns(session, scope.workspace_id, scope.idea_id)
    parts = [f"Idea title: {idea.title}\n\nIdea text:\n{idea.raw_text}"]
    parts.append("Interview brief:\n" + (brief.model_dump_json() if brief is not None else "none"))
    answered = [t for t in turns if t.answer]
    if answered:
        parts.append(
            "What the user said:\n" + "\n".join(f"- {t.question} {t.answer}" for t in answered)
        )
    parts.append(await _research_text(session, scope, book))
    return parts


async def _research_text(session: AsyncSession, scope: ResearchScope, book: SourceBook) -> str:
    snapshot = await research.latest_snapshot(session, scope.workspace_id, scope.idea_id)
    if snapshot is None:
        return "Research: none was done for this idea."
    book.add(c.url for c in snapshot.competitors)
    book.add(i.url for i in snapshot.items if i.url)
    lines = [f"Research summary: {snapshot.summary or 'none'}"]
    lines += [
        f"- competitor {c.name} ({c.url}), overlap {c.overlap}, pricing {c.pricing or 'unknown'}: "
        f"{c.description or ''}"
        for c in snapshot.competitors
    ]
    lines += [
        f'- {i.kind.value} "{i.title}" ({i.url or "no url"}), confidence {i.confidence}: '
        f"{i.claim} Quote: {i.quote or 'none'}"
        for i in snapshot.items
    ]
    return "Research:\n" + "\n".join(lines)
