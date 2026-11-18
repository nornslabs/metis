"""Competitor KB rules: dedupe by normalized domain, lookup by embedding and by name.

Every function takes the caller's ``AsyncSession``, flushes but never commits and is scoped
to the workspace id as well as RLS. Embeddings come from the caller (the Researcher embeds
through the LLM gateway); this module never calls a model.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.helpers.validation import validate_input
from metis.modules.research import repo
from metis.modules.research.dto import (
    DEFAULT_KB_MATCHES,
    Competitor,
    KbMatch,
    KbMatchKind,
    KbQuery,
    NewCompetitor,
)
from metis.modules.research.helpers.domain import normalize_domain


async def upsert_competitor(
    session: AsyncSession, workspace_id: UUID, competitor: NewCompetitor
) -> Competitor:
    """Add a competitor, or refresh the one with the same normalized domain.

    A refresh keeps the id, takes the new name and URL, and keeps the stored description,
    pricing and embedding where the new ones are missing.
    """
    row = await repo.competitors.upsert(
        session,
        workspace_id,
        name=competitor.name,
        url=competitor.url,
        domain=normalize_domain(competitor.url),
        description=competitor.description,
        pricing=competitor.pricing,
        embedding=competitor.embedding,
    )
    return Competitor.model_validate(row)


async def kb_lookup(
    session: AsyncSession,
    workspace_id: UUID,
    query: str,
    k: int = DEFAULT_KB_MATCHES,
    query_embedding: Sequence[float] | None = None,
) -> list[KbMatch]:
    """Up to ``k`` KB competitors for ``query``.

    With ``query_embedding``: the nearest competitors by cosine similarity first, then
    name or domain matches not already found. Without it: name or domain matches only.
    """
    lookup = validate_input(
        KbQuery,
        query=query,
        k=k,
        query_embedding=tuple(query_embedding) if query_embedding is not None else None,
    )
    matches: list[KbMatch] = []
    if lookup.query_embedding is not None:
        nearest = await repo.competitors.nearest(
            session, workspace_id, lookup.query_embedding, lookup.k
        )
        matches = [
            KbMatch(
                competitor=Competitor.model_validate(row),
                score=1.0 - distance,
                matched_by=KbMatchKind.EMBEDDING,
            )
            for row, distance in nearest
        ]
    found = {match.competitor.id for match in matches}
    if len(matches) < lookup.k:
        named = await repo.competitors.matching_name(session, workspace_id, lookup.query, lookup.k)
        matches += [
            KbMatch(
                competitor=Competitor.model_validate(row), score=None, matched_by=KbMatchKind.NAME
            )
            for row in named
            if row.id not in found
        ]
    return matches[: lookup.k]
