"""The Researcher's own tools: look up the competitor KB, save a competitor, save an item, finish.

Each tool works on one run (``ResearchScope``) and opens its own short, committed
transaction, so nothing is held open while the run waits on Exa or the model. They call only
the ``research`` module's public surface; the rules (a competitor or market fact needs a
source URL, a closed snapshot takes no writes) live there, and a tool only turns a refusal
into a message the model can act on. The run's snapshot is opened on demand: opening is
idempotent, so a second pass and a crash-recovery re-run add to the same snapshot.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import date
from typing import Annotated
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from metis.agent.llm import LLMGateway
from metis.core.errors import MetisError, UpstreamError
from metis.core.logging import get_logger
from metis.modules import research
from metis.modules.research import NewCompetitor, NewResearchItem, ResearchItemKind

KB_LOOKUP = "kb_lookup"
KB_UPSERT_COMPETITOR = "kb_upsert_competitor"
SAVE_RESEARCH_ITEM = "save_research_item"
FINISH_RESEARCH = "finish_research"
MAX_CLARIFICATION_QUESTIONS = 2
MAX_QUESTION_LENGTH = 500
DEFAULT_KB_RESULTS = 5
MAX_KB_RESULTS = 10
QUOTE_NEEDED = (
    "The item was not saved: a competitor or market_fact needs a quote, the sentence from the "
    "source that supports the claim."
)
QUOTED_KINDS = frozenset({ResearchItemKind.COMPETITOR, ResearchItemKind.MARKET_FACT})
SAVED = "Saved."
FINISHED = "Research finished."

logger = get_logger(__name__)

SessionOpener = Callable[[UUID], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True)
class ResearchScope:
    """The run the tools work on, how to open a workspace-scoped session, and its gateway."""

    workspace_id: UUID
    idea_id: UUID
    run_id: UUID
    open_session: SessionOpener
    gateway: LLMGateway

    def session(self) -> AbstractAsyncContextManager[AsyncSession]:
        return self.open_session(self.workspace_id)


class KbLookupArgs(BaseModel):
    query: str = Field(min_length=1, max_length=200, description="A product name, domain or idea.")
    k: int = Field(default=DEFAULT_KB_RESULTS, ge=1, le=MAX_KB_RESULTS)


class UpsertCompetitorArgs(BaseModel):
    name: str
    url: str = Field(description="The competitor's own website.")
    description: str | None = Field(default=None, description="What it does, in a sentence.")
    pricing: str | None = Field(default=None, description="Pricing, only if found.")
    overlap: float = Field(ge=0, le=1, description="How much it overlaps with the idea, 0 to 1.")


class SaveItemArgs(BaseModel):
    kind: ResearchItemKind
    title: str
    url: str | None = Field(
        default=None, description="The source page. Required for competitor and market_fact."
    )
    published_at: date | None = None
    quote: str | None = Field(default=None, description="The sentence that supports the claim.")
    claim: str = Field(description="The finding, in one or two sentences.")
    confidence: float = Field(ge=0, le=1, description="How sure the source makes you, 0 to 1.")


class ResearchFinish(BaseModel):
    """The Researcher's structured output."""

    summary: str = Field(
        default="", description="Top competitors, demand signals and risks, in a few sentences."
    )
    no_direct_competitors: bool = Field(
        default=False, description="True when no direct competitor was found."
    )
    needs_clarification: list[
        Annotated[str, Field(min_length=1, max_length=MAX_QUESTION_LENGTH)]
    ] = Field(
        default_factory=list,
        max_length=MAX_CLARIFICATION_QUESTIONS,
        description="Up to two short questions only the user can answer. Usually none.",
    )


async def open_run_snapshot(
    session: AsyncSession, scope: ResearchScope
) -> research.ResearchSnapshot:
    """The run's open snapshot (opened if needed; safe to call again)."""
    return await research.open_snapshot(session, scope.workspace_id, scope.idea_id, scope.run_id)


def research_tools(scope: ResearchScope) -> list[BaseTool]:
    """The Researcher's own allow-list (the Exa tools are added by the node)."""
    return [kb_lookup_tool(scope), _upsert_competitor(scope), _save_item(scope), _finish()]


async def _embed(
    scope: ResearchScope, session: AsyncSession, texts: Sequence[str]
) -> list[float] | None:
    """One vector for ``texts`` joined, or ``None`` when embeddings are off or fail."""
    try:
        vectors = await scope.gateway.embed(session, [" ".join(texts)])
    except UpstreamError:
        logger.warning("research.embedding_failed")
        return None
    return vectors[0] if vectors else None


def kb_lookup_tool(scope: ResearchScope) -> BaseTool:
    async def kb_lookup(query: str, k: int = DEFAULT_KB_RESULTS) -> str:
        async with scope.session() as session:
            embedding = await _embed(scope, session, [query])
            try:
                matches = await research.kb_lookup(
                    session, scope.workspace_id, query, k, query_embedding=embedding
                )
            except MetisError as exc:
                return f"The lookup was refused: {exc}"
        return json.dumps(
            [
                {
                    "id": str(m.competitor.id),
                    "name": m.competitor.name,
                    "url": m.competitor.url,
                    "description": m.competitor.description,
                    "pricing": m.competitor.pricing,
                    "score": m.score,
                    "matched_by": m.matched_by.value,
                }
                for m in matches
            ]
        )

    return StructuredTool.from_function(
        coroutine=kb_lookup,
        name=KB_LOOKUP,
        description=(
            "Look in the workspace's competitor knowledge base before searching the web. "
            "Returns competitors found in earlier research."
        ),
        args_schema=KbLookupArgs,
    )


def _upsert_competitor(scope: ResearchScope) -> BaseTool:
    async def kb_upsert_competitor(
        name: str,
        url: str,
        overlap: float,
        description: str | None = None,
        pricing: str | None = None,
    ) -> str:
        async with scope.session() as session:
            embedding = await _embed(scope, session, [name, description or ""])
            try:
                snapshot = await open_run_snapshot(session, scope)
                competitor = await research.upsert_competitor(
                    session,
                    scope.workspace_id,
                    NewCompetitor(
                        name=name,
                        url=url,
                        description=description,
                        pricing=pricing,
                        embedding=tuple(embedding) if embedding else None,
                    ),
                )
                await research.link_competitor(
                    session, scope.workspace_id, snapshot.id, competitor.id, overlap
                )
            except (MetisError, ValueError) as exc:
                return f"The competitor was not saved: {exc}"
        return json.dumps({"id": str(competitor.id), "name": competitor.name})

    return StructuredTool.from_function(
        coroutine=kb_upsert_competitor,
        name=KB_UPSERT_COMPETITOR,
        description=(
            "Save a competitor to the knowledge base and link it to this idea with its overlap. "
            "A competitor already in the knowledge base (same website) is refreshed, not copied."
        ),
        args_schema=UpsertCompetitorArgs,
    )


def _save_item(scope: ResearchScope) -> BaseTool:
    async def save_research_item(
        kind: ResearchItemKind,
        title: str,
        claim: str,
        confidence: float,
        url: str | None = None,
        published_at: date | None = None,
        quote: str | None = None,
    ) -> str:
        if kind in QUOTED_KINDS and not (quote and quote.strip()):
            return QUOTE_NEEDED
        async with scope.session() as session:
            try:
                snapshot = await open_run_snapshot(session, scope)
                await research.add_item(
                    session,
                    scope.workspace_id,
                    snapshot.id,
                    NewResearchItem(
                        kind=kind,
                        title=title,
                        url=url,
                        published_at=published_at,
                        quote=quote,
                        claim=claim,
                        confidence=confidence,
                    ),
                )
            except (MetisError, ValueError) as exc:
                return f"The item was not saved: {exc}"
        return SAVED

    return StructuredTool.from_function(
        coroutine=save_research_item,
        name=SAVE_RESEARCH_ITEM,
        description=(
            "Save one finding (competitor, market_fact, trend or risk). A competitor or "
            "market_fact without a source URL and a supporting quote is refused."
        ),
        args_schema=SaveItemArgs,
    )


def _finish() -> BaseTool:
    async def finish_research(**_: object) -> str:
        # The node reads the output from this call once research ends.
        return FINISHED

    return StructuredTool.from_function(
        coroutine=finish_research,
        name=FINISH_RESEARCH,
        description=(
            "End the research with a short summary. Ask for clarification only when an answer "
            "from the user would change the research."
        ),
        args_schema=ResearchFinish,
    )
