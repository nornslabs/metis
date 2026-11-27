"""The Scorer: six evidence-backed marks for the idea, stored as one immutable score run.

At ``scoring`` it runs a tool-calling loop (``build_react_specialist``) over the scorer prompt,
the rubric and KB tools, a capped web search (``MAX_SEARCH_CALLS`` per run, its own counter) and
the run's ``score`` chat model, seeded with the idea, its interview brief, the user's answers
and the latest research snapshot. ``submit_scores`` ends the loop; the ``scoring`` module
computes the total and band. The node then routes by band: ``advising`` below 75 (the Advisor
has not been yet), else ``spec_draft``. The runner copies the stage to ``ideas.stage``; the node
does not.

A run stores one score run, plus one more when the Advisor asks for a rescore
(``rescore_after`` names the score run it advised): a node entered when this run already has a
score run makes no model call and only routes, which covers a crash re-run and the pass after
the Advisor. The rescore reuses the research and has its own search budget. Without an Exa key
the loop runs without the search tool. A loop that ends with no stored score (two refused
submissions, or none) fails the run with ``score.invalid_submission``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.tools import BaseTool
from langgraph.config import get_stream_writer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from metis.agent.llm import LLMGateway
from metis.agent.prompts import load_specialist_prompt
from metis.agent.specialists.base import build_react_specialist, invoke_loop
from metis.agent.specialists.stubs import ADVISED_MARKER, SpecialistNode
from metis.agent.state import MetisState
from metis.agent.supervisor import Specialist
from metis.agent.tools.exa import (
    ExaCallBudget,
    exa_tools_for,
    open_exa_tools,
    ready_exa_key,
    with_call_cap,
)
from metis.agent.tools.research_kb import ResearchScope, SessionOpener, kb_lookup_tool
from metis.agent.tools.scoring import (
    SUBMIT_SCORES,
    ScoreRefused,
    SourceBook,
    SubmissionLedger,
    collect_search_urls,
    scoring_tools,
)
from metis.core.errors import ErrorCode
from metis.core.events import RunEventType
from metis.core.logging import get_logger
from metis.core.ports import LLMProvider
from metis.helpers.http import ClientFactory
from metis.modules import ideas, research, scoring
from metis.modules.ideas import RunKind, Stage
from metis.modules.scoring import ScoreBand, ScoreRun

PROMPT = "scorer"
PURPOSE = "score"
MAX_SEARCH_CALLS = 3
SEARCH_COUNTER = "score_searches"
RESCORE_SEARCH_COUNTER = "score_searches_rescore"
# Graph supersteps: a few lookups and searches, then the submission (and one retry).
STEP_LIMIT = 30
SEARCH_CAP_MESSAGE = (
    f"The web search limit ({MAX_SEARCH_CALLS} calls) is reached; this call was not made. "
    f"Submit the scores now with {SUBMIT_SCORES}."
)
NO_SEARCH_NOTE = "Web search is not available in this run; use only the research above."

logger = get_logger(__name__)


def build_scorer(
    gateway: LLMGateway,
    open_session: SessionOpener,
    redis: Redis,
    make_exa_client: ClientFactory,
) -> SpecialistNode:
    """The Scorer node for one run."""

    async def node(state: MetisState) -> dict[str, Any]:
        scope = ResearchScope(
            workspace_id=UUID(state["workspace_id"]),
            idea_id=UUID(state["idea_id"]),
            run_id=UUID(state["run_id"]),
            open_session=open_session,
            gateway=gateway,
        )
        existing = await _score_of_this_run(scope)
        rescore = _rescore_wanted(existing, state)
        if existing is not None and not rescore:
            logger.info("score.already_recorded")
            return _finish_node(
                state, {"stage": _next_stage(existing, state), "rescore_after": None}
            )
        ledger = SubmissionLedger()
        omit_previous_research = state.get("run_kind") == RunKind.MARKET_RECHECK and state.get(
            "research_skipped", False
        )
        counter = RESCORE_SEARCH_COUNTER if rescore else SEARCH_COUNTER
        if not await _score(
            scope,
            redis,
            make_exa_client,
            ledger,
            counter,
            omit_previous_research=omit_previous_research,
        ):
            logger.warning("score.step_limit_reached")
            return _finish_node(state, {"last_error": ErrorCode.RUN_STEP_LIMIT_REACHED.value})
        if ledger.recorded is None:
            logger.warning("score.no_valid_submission", refusals=ledger.refusals)
            return _finish_node(state, {"last_error": ErrorCode.SCORE_INVALID_SUBMISSION.value})
        recorded = ledger.recorded
        get_stream_writer()(
            {
                "type": RunEventType.SCORE.value,
                "score_run_id": str(recorded.id),
                "total": recorded.total,
                "band": recorded.band.value,
            }
        )
        return _finish_node(state, {"stage": _next_stage(recorded, state), "rescore_after": None})

    return node


async def _score(
    scope: ResearchScope,
    redis: Redis,
    make_exa_client: ClientFactory,
    ledger: SubmissionLedger,
    counter: str,
    *,
    omit_previous_research: bool = False,
) -> bool:
    """Run the loop; ``False`` when it hit its step limit."""
    book = SourceBook()
    async with scope.session() as session:
        api_key = await ready_exa_key(session, scope.workspace_id)
        model = await scope.gateway.chat_model(session, PURPOSE)
        seed = await _seed(
            session,
            scope,
            book,
            searching=api_key is not None,
            omit_previous_research=omit_previous_research,
        )
    own_tools = [kb_lookup_tool(scope), *scoring_tools(scope, book, ledger)]
    if api_key is None:
        return await _loop(model, own_tools, seed)
    budget = ExaCallBudget(redis, scope.run_id, MAX_SEARCH_CALLS, counter)
    async with open_exa_tools(api_key, scope.run_id, redis, make_exa_client) as exa_tools:
        search = collect_search_urls(
            with_call_cap(
                exa_tools_for(Specialist.SCORER.value, exa_tools),
                budget,
                limit_message=SEARCH_CAP_MESSAGE,
            ),
            book,
        )
        return await _loop(model, [*search, *own_tools], seed)


async def _loop(model: LLMProvider, tools: list[BaseTool], seed: str) -> bool:
    """Run the loop; ``False`` when it hit its step limit."""
    loop = build_react_specialist(
        load_specialist_prompt(PROMPT),
        tools,
        model,
        step_limit=STEP_LIMIT,
        finish_tools={SUBMIT_SCORES},
        refusals=(ScoreRefused,),
    )
    return await invoke_loop(loop, seed)


async def _score_of_this_run(scope: ResearchScope) -> ScoreRun | None:
    async with scope.session() as session:
        latest = await scoring.latest_score(session, scope.workspace_id, scope.idea_id)
    return latest if latest is not None and latest.run_id == scope.run_id else None


async def _seed(
    session: AsyncSession,
    scope: ResearchScope,
    book: SourceBook,
    *,
    searching: bool,
    omit_previous_research: bool = False,
) -> str:
    """What the model starts from; also fills ``book`` with the research's own URLs."""
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
    if omit_previous_research:
        parts.append(
            "Fresh market research is unavailable because Exa is not configured. "
            "Older research was intentionally omitted; do not cite it. Mark unsupported "
            "parameters as no_evidence with appropriately low confidence."
        )
    else:
        parts.append(await _research_text(session, scope, book))
    if not searching:
        parts.append(NO_SEARCH_NOTE)
    return "\n\n".join(parts)


def _rescore_wanted(existing: ScoreRun | None, state: MetisState) -> bool:
    """The Advisor asked for a rescore and the score it advised on is still the newest."""
    advised = state.get("rescore_after")
    return existing is not None and advised is not None and str(existing.id) == advised


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


def _next_stage(score: ScoreRun, state: MetisState) -> Stage:
    """``advising`` below 75 unless the Advisor has already been; else the spec."""
    advised = ADVISED_MARKER in state["summary"]
    return Stage.SPEC_DRAFT if score.band is ScoreBand.BUILD or advised else Stage.ADVISING


def _finish_node(state: MetisState, update: dict[str, Any]) -> dict[str, Any]:
    get_stream_writer()({"type": RunEventType.NODE_FINISHED.value, "node": Specialist.SCORER.value})
    if state.get("run_kind") in {RunKind.RESCORE, RunKind.MARKET_RECHECK}:
        update = {**update, "refresh_complete": True}
    return {**update, "step_count": state["step_count"] + 1}
