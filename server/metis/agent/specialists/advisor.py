"""The Advisor: sourced suggestions that would make a weak idea stronger.

At ``advising`` it reads the idea's newest score run and runs a tool-calling loop
(``build_react_specialist``) over the advisor prompt, a KB lookup, a capped web search
(``MAX_SEARCH_CALLS`` per run, its own counter) and ``save_suggestion`` / ``finish_advice``, on
the run's ``advise`` chat model. It is seeded with the idea, its interview, the research, the
score and the weakest parameters (computed in code). A score below 55 owes 3–5 suggestions, a
promising one at most 2; a loop that ends short for a score below 55 fails the run with
``advice.invalid_submission``.

Below 55 the node then pauses on an ``advice_decision`` interrupt: ``revise`` saves the user's
new text (accepted suggestions appended as notes) and sends the run back to the Scorer, which
scores again once; ``continue`` goes on to the spec; ``stop`` ends the run with the idea left at
``advising``. A promising idea goes straight on to the spec. One Advisor pass per run.

Every suggestion passes the ``advice_output`` gate before it is saved (``tools/advice_gate.py``);
a suggestion the gate skips is not saved and never fails the run. A score below 55 that ends
short of its minimum only because of skips (with at least one suggestion saved) goes on to the
decision with what is saved.

The node is safe to re-run: with enough suggestions saved for the score (or a shortfall that
gate skips caused, counted in Redis) it makes no model call, so a crash re-run and the re-run
after the interrupt resumes never add advice twice, and the revision write gives the same result
when repeated.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.tools import BaseTool
from langgraph.config import get_stream_writer
from langgraph.types import interrupt
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from metis.agent.gate import GateRefusal, build_gate_context
from metis.agent.llm import LLMGateway
from metis.agent.prompts import load_specialist_prompt
from metis.agent.specialists.base import build_react_specialist, invoke_loop
from metis.agent.specialists.idea_context import idea_seed_parts
from metis.agent.specialists.stubs import ADVISED_MARKER, SpecialistNode
from metis.agent.state import MetisState
from metis.agent.supervisor import Specialist
from metis.agent.tools.advice import (
    FINISH_ADVICE,
    AdviceLedger,
    AdvicePlan,
    AdviceRefused,
    AdviceReview,
    SkipCounter,
    advice_tools,
    plan_for,
)
from metis.agent.tools.advice_gate import AdviceBrief, WeakParam, build_advice_gate
from metis.agent.tools.ask_user import ADVICE_DECISION
from metis.agent.tools.exa import (
    ExaCallBudget,
    exa_tools_for,
    open_exa_tools,
    ready_exa_key,
    with_call_cap,
)
from metis.agent.tools.research_kb import ResearchScope, SessionOpener, kb_lookup_tool
from metis.agent.tools.scoring import SourceBook, collect_search_urls
from metis.core.errors import ErrorCode
from metis.core.events import RunEventType
from metis.core.logging import get_logger
from metis.core.ports import LLMProvider
from metis.helpers.http import ClientFactory
from metis.modules import ideas, scoring
from metis.modules.ideas import MAX_RAW_TEXT_LENGTH, AdviceDecision, AdviceResume, Stage
from metis.modules.scoring import ScoreRun, Suggestion, SuggestionStatus

PROMPT = "advisor"
PURPOSE = "advise"
MAX_SEARCH_CALLS = 3
SEARCH_COUNTER = "advise_searches"
# Graph supersteps: lookups and searches, up to five saves, the finish (and one retry).
STEP_LIMIT = 40
NOTES_HEADING = "Accepted improvements:"
NOTICE_NOTES_DROPPED = "advice.notes_dropped"
NOTICE_NOTES_DROPPED_TEXT = "The accepted suggestions were not added: the idea text is too long."
SEARCH_CAP_MESSAGE = (
    f"The web search limit ({MAX_SEARCH_CALLS} calls) is reached; this call was not made. "
    f"Save your suggestions, then call {FINISH_ADVICE}."
)
NO_SEARCH_NOTE = "Web search is not available in this run; use only the research and the score."

logger = get_logger(__name__)


def build_advisor(
    gateway: LLMGateway,
    open_session: SessionOpener,
    redis: Redis,
    make_exa_client: ClientFactory,
) -> SpecialistNode:
    """The Advisor node for one run."""

    async def node(state: MetisState) -> dict[str, Any]:
        scope = ResearchScope(
            workspace_id=UUID(state["workspace_id"]),
            idea_id=UUID(state["idea_id"]),
            run_id=UUID(state["run_id"]),
            open_session=open_session,
            gateway=gateway,
        )
        async with scope.session() as session:
            score = await scoring.latest_score(session, scope.workspace_id, scope.idea_id)
        plan = None if score is None else plan_for(score)
        if plan is None:
            logger.info("advice.not_needed")
            return _finish_node(state, _go_on(state, Stage.SPEC_DRAFT))
        ledger = AdviceLedger(saved=await _saved_ids(scope, plan.score.id))
        skips = SkipCounter(redis, scope.run_id, plan.score.id)
        if not _settled(plan, ledger, await skips.count()):
            failure = await _advise(scope, redis, make_exa_client, plan, ledger, skips)
            if failure is not None:
                return _finish_node(state, {"last_error": failure})
        if plan.score.band is not scoring.ScoreBand.ADVISE:
            return _finish_node(state, _go_on(state, Stage.SPEC_DRAFT))
        decision = _ask(plan, ledger)
        return _finish_node(state, await _apply(scope, state, plan, decision))

    return node


async def _advise(
    scope: ResearchScope,
    redis: Redis,
    make_exa_client: ClientFactory,
    plan: AdvicePlan,
    ledger: AdviceLedger,
    skips: SkipCounter,
) -> str | None:
    """Run the loop; the error code to fail the run with, or ``None`` when the advice is done."""
    book = SourceBook()
    async with scope.session() as session:
        api_key = await ready_exa_key(session, scope.workspace_id)
        model = await scope.gateway.chat_model(session, PURPOSE)
        seed = await _seed(session, scope, book, plan, ledger, searching=api_key is not None)
        review = AdviceReview(
            gate=build_advice_gate(book),
            context=await build_gate_context(scope.gateway, session, redis, scope.run_id),
            brief=await _brief(session, scope, plan),
            skips=skips,
        )
    own_tools = [kb_lookup_tool(scope), *advice_tools(scope, plan, review, ledger)]
    if api_key is None:
        finished = await _loop(model, own_tools, seed)
    else:
        budget = ExaCallBudget(redis, scope.run_id, MAX_SEARCH_CALLS, SEARCH_COUNTER)
        async with open_exa_tools(api_key, scope.run_id, redis, make_exa_client) as exa_tools:
            search = collect_search_urls(
                with_call_cap(
                    exa_tools_for(Specialist.ADVISOR.value, exa_tools),
                    budget,
                    limit_message=SEARCH_CAP_MESSAGE,
                ),
                book,
            )
            finished = await _loop(model, [*search, *own_tools], seed)
    if not finished:
        logger.warning("advice.step_limit_reached")
        # Advice for a promising idea is optional: it never fails the run.
        return None if plan.minimum == 0 else ErrorCode.RUN_STEP_LIMIT_REACHED.value
    if len(ledger.saved) < plan.minimum:
        if ledger.skipped and ledger.saved:
            logger.info("advice.short_after_gate_skips", saved=len(ledger.saved))
            return None
        logger.warning(
            "advice.too_few_suggestions", saved=len(ledger.saved), refusals=ledger.refusals
        )
        return ErrorCode.ADVICE_INVALID_SUBMISSION.value
    return None


def _settled(plan: AdvicePlan, ledger: AdviceLedger, skipped: int) -> bool:
    """Whether the advice for this score is done: enough saved, or short only through skips."""
    if len(ledger.saved) >= max(plan.minimum, 1):
        return True
    return skipped > 0 and (bool(ledger.saved) or plan.minimum == 0)


async def _loop(model: LLMProvider, tools: list[BaseTool], seed: str) -> bool:
    """Run the loop; ``False`` when it hit its step limit."""
    loop = build_react_specialist(
        load_specialist_prompt(PROMPT),
        tools,
        model,
        step_limit=STEP_LIMIT,
        finish_tools={FINISH_ADVICE},
        refusals=(AdviceRefused, GateRefusal),
    )
    return await invoke_loop(loop, seed)


def _ask(plan: AdvicePlan, ledger: AdviceLedger) -> AdviceResume:
    """Pause for the user's decision. Nothing may run before this that cannot be repeated."""
    answer = interrupt(
        {
            "type": ADVICE_DECISION,
            "score_run_id": str(plan.score.id),
            "total": plan.score.total,
            "band": plan.score.band.value,
            "suggestion_ids": [str(suggestion_id) for suggestion_id in ledger.saved],
        }
    )
    return AdviceResume.model_validate(answer)


async def _apply(
    scope: ResearchScope, state: MetisState, plan: AdvicePlan, decision: AdviceResume
) -> dict[str, Any]:
    """The state update for the user's decision (a revision is saved first)."""
    if decision.decision is AdviceDecision.CONTINUE:
        return _go_on(state, Stage.SPEC_DRAFT)
    if decision.decision is AdviceDecision.STOP:
        return {"summary": _advised(state), "advice_stopped": True}
    await _revise(scope, plan, decision)
    return {**_go_on(state, Stage.SCORING), "rescore_after": str(plan.score.id)}


async def _revise(scope: ResearchScope, plan: AdvicePlan, decision: AdviceResume) -> None:
    """Save the user's new text with the accepted suggestions as notes; mark them accepted."""
    async with scope.session() as session:
        listed = await scoring.list_suggestions(
            session, scope.workspace_id, scope.idea_id, plan.score.id
        )
        wanted = set(decision.accepted_suggestion_ids)
        accepted = [s for s in listed.items if s.id in wanted]
        text, notes_fit = _revised_text(decision.revised_text or "", accepted)
        await ideas.apply_revision(session, scope.workspace_id, scope.idea_id, text)
        for suggestion in accepted:
            await scoring.set_suggestion_status(
                session, scope.workspace_id, suggestion.id, SuggestionStatus.ACCEPTED
            )
    if not notes_fit:
        get_stream_writer()(
            {
                "type": RunEventType.NOTICE.value,
                "code": NOTICE_NOTES_DROPPED,
                "text": NOTICE_NOTES_DROPPED_TEXT,
            }
        )


def _revised_text(revised: str, accepted: list[Suggestion]) -> tuple[str, bool]:
    """The idea's new text, and whether the accepted suggestions fit after it as notes."""
    base = revised.strip()
    if not accepted:
        return base, True
    notes = "\n".join(f"- {s.title}: {s.rationale}" for s in accepted)
    combined = f"{base}\n\n{NOTES_HEADING}\n{notes}"
    if len(combined) > MAX_RAW_TEXT_LENGTH:
        return base, False
    return combined, True


async def _saved_ids(scope: ResearchScope, score_run_id: UUID) -> list[UUID]:
    async with scope.session() as session:
        listed = await scoring.list_suggestions(
            session, scope.workspace_id, scope.idea_id, score_run_id
        )
    return [suggestion.id for suggestion in listed.items]


async def _seed(
    session: AsyncSession,
    scope: ResearchScope,
    book: SourceBook,
    plan: AdvicePlan,
    ledger: AdviceLedger,
    *,
    searching: bool,
) -> str:
    """What the model starts from; also fills ``book`` with the research's and score's URLs."""
    parts = await idea_seed_parts(session, scope, book)
    parts.append(_score_text(plan.score, book))
    weakest = ", ".join(p.value for p in plan.targets)
    wanted = (
        f"Save {plan.minimum} to {plan.maximum} suggestions."
        if plan.minimum
        else f"Save at most {plan.maximum} suggestions (none is fine if nothing is well founded)."
    )
    parts.append(
        f"Band: {plan.score.band.value}. Weakest parameters, worst first: {weakest}. {wanted}"
    )
    if ledger.saved:
        parts.append(f"{len(ledger.saved)} suggestions are already saved for this score.")
    if not searching:
        parts.append(NO_SEARCH_NOTE)
    return "\n\n".join(parts)


async def _brief(session: AsyncSession, scope: ResearchScope, plan: AdvicePlan) -> AdviceBrief:
    """What the gate's judge reads: the idea and the weakest parameters with the score's reasons."""
    idea = await ideas.get_idea(session, scope.workspace_id, scope.idea_id)
    by_param = {result.param: result for result in plan.score.params}
    weakest = tuple(
        WeakParam(param, by_param[param].raw, by_param[param].reason) for param in plan.targets
    )
    return AdviceBrief(idea.title, idea.raw_text, weakest)


def _score_text(score: ScoreRun, book: SourceBook) -> str:
    lines = [f"Score: {score.total} of 100 ({score.band.value})."]
    for param in score.params:
        book.add(item.url for item in param.evidence)
        sources = ", ".join(item.url for item in param.evidence) or "none"
        lines.append(
            f"- {param.param.value} (weight {param.weight}): {param.raw}/10, confidence "
            f"{param.confidence}. {param.reason} Sources: {sources}"
        )
    return "\n".join(lines)


def _advised(state: MetisState) -> str:
    summary = state["summary"]
    return summary if ADVISED_MARKER in summary else f"{summary} {ADVISED_MARKER}".strip()


def _go_on(state: MetisState, stage: Stage) -> dict[str, Any]:
    return {"stage": stage, "summary": _advised(state)}


def _finish_node(state: MetisState, update: dict[str, Any]) -> dict[str, Any]:
    get_stream_writer()(
        {"type": RunEventType.NODE_FINISHED.value, "node": Specialist.ADVISOR.value}
    )
    return {**update, "step_count": state["step_count"] + 1}
