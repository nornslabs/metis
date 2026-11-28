"""The Researcher: competitors and market facts for the idea, with sources.

At ``researching`` it runs a tool-calling loop (``build_react_specialist``) over the
researcher prompt, the workspace's Exa tools (capped at ``MAX_EXA_CALLS`` calls per run), the
KB and item tools, and the run's ``research`` chat model, seeded with the idea, its
interview brief and what earlier passes saved. ``finish_research`` ends the loop. The node then
either asks for one clarification round (the questions go in state; the supervisor sends the
run to the Interviewer and back) or closes the snapshot with the summary and moves the run to
``scoring``. The runner copies the stage to ``ideas.stage``; the node does not.

Without an Exa key the node does no research: it publishes a ``notice`` event, sets
``research_skipped`` (the supervisor then ends the run) and leaves the stage at
``researching``, so a later run, once a key is saved, starts there.

The loop never pauses for the user, so the node runs from start to end; after a crash it
re-runs, reusing the run's open snapshot and the cached Exa calls. No database transaction is
open while the loop runs: the Exa key is read first in its own short one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.config import get_stream_writer
from langgraph.errors import GraphRecursionError
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from metis.adapters.feature_flags import build_feature_flag_provider
from metis.agent.gate import GateRefusal, build_gate_context
from metis.agent.llm import LLMGateway
from metis.agent.prompts import load_specialist_prompt
from metis.agent.specialists.base import build_react_specialist, finished_call_args
from metis.agent.specialists.stubs import SpecialistNode
from metis.agent.state import MetisState
from metis.agent.supervisor import Specialist
from metis.agent.tools.exa import PROVIDER as EXA_PROVIDER
from metis.agent.tools.exa import ExaCallBudget, exa_tools_for, open_exa_tools, with_call_cap
from metis.agent.tools.research_gates import (
    CallMemory,
    kb_lookup_for,
    load_run_knowledge,
    with_kb_matches,
    with_research_gate,
)
from metis.agent.tools.research_kb import (
    FINISH_RESEARCH,
    MAX_CLARIFICATION_QUESTIONS,
    ResearchFinish,
    ResearchScope,
    SessionOpener,
    open_run_snapshot,
    research_tools,
)
from metis.core.config import get_settings
from metis.core.errors import ErrorCode, UpstreamError
from metis.core.events import RunEventType
from metis.core.logging import get_logger
from metis.core.ports import FeatureFlagProvider, FlagContext
from metis.helpers.http import ClientFactory
from metis.modules import ideas, research
from metis.modules.ideas import RunKind, Stage
from metis.modules.identity import KeyReadiness, ProviderKind, get_key_for_use, key_readiness

PROMPT = "researcher"
PURPOSE = "research"
MAX_EXA_CALLS = 12
# Graph supersteps for one pass: 12 Exa calls, KB lookups and saves, each a model call and a
# tool step. The Exa cap, not this, is what bounds the research.
STEP_LIMIT = 80
SUMMARY_LIMIT = 4_000
NOTICE_SKIPPED_NO_EXA = "research.skipped_no_exa"
NOTICE_SKIPPED_NO_EXA_TEXT = "Research is skipped: Exa isn't set up."
NOTICE_PARTIAL_EXA_LOST = "research.partial_exa_lost"
NOTICE_PARTIAL_EXA_LOST_TEXT = (
    "Web search stopped part-way, so research is incomplete. Continuing with what was found."
)
EXA_LOST_SUMMARY = "Research stopped early: web search failed part-way. Findings may be incomplete."
NO_COMPETITORS_NOTE = "No direct competitors found."
NO_SUMMARY = "Research ended without a summary."
CAP_MESSAGE = (
    f"The web search limit ({MAX_EXA_CALLS} calls) is reached; this call was not made. "
    f"Save what you found, then call {FINISH_RESEARCH}."
)

logger = get_logger(__name__)


def build_researcher(
    gateway: LLMGateway,
    open_session: SessionOpener,
    redis: Redis,
    make_exa_client: ClientFactory,
    flags: FeatureFlagProvider | None = None,
) -> SpecialistNode:
    """The Researcher node for one run."""
    _flags = flags or build_feature_flag_provider(get_settings())
    settings = get_settings()

    async def node(state: MetisState) -> dict[str, Any]:
        scope = ResearchScope(
            workspace_id=UUID(state["workspace_id"]),
            idea_id=UUID(state["idea_id"]),
            run_id=UUID(state["run_id"]),
            open_session=open_session,
            gateway=gateway,
        )
        flag_context = FlagContext(
            workspace_id=scope.workspace_id,
            environment=settings.app_env,
            custom_attributes={},
        )
        if not await _flags.is_enabled("exa_enabled", flag_context, default=True):
            logger.info("research.skipped_exa_disabled")
            get_stream_writer()(
                {
                    "type": RunEventType.NOTICE.value,
                    "code": NOTICE_SKIPPED_NO_EXA,
                    "text": "Research is skipped: the exa_enabled kill switch is off.",
                }
            )
            return _finish_node(state, {"research_skipped": True})
        if await _exa_key_missing(scope):
            logger.info("research.skipped_no_exa")
            get_stream_writer()(
                {
                    "type": RunEventType.NOTICE.value,
                    "code": NOTICE_SKIPPED_NO_EXA,
                    "text": NOTICE_SKIPPED_NO_EXA_TEXT,
                }
            )
            return _finish_node(state, {"research_skipped": True})
        if await _already_closed(scope):
            # A crash after the snapshot closed but before the checkpoint: do not research again.
            logger.info("research.already_closed")
            return _finish_node(state, {"stage": Stage.SCORING})
        budget = ExaCallBudget(redis, scope.run_id, MAX_EXA_CALLS)
        outcome = await _research(scope, redis, make_exa_client, budget)
        if outcome.end is _LoopEnd.EXA_LOST:
            return await _close_partial(state, scope)
        if outcome.end is _LoopEnd.STEP_LIMIT:
            logger.warning("research.step_limit_reached")
            return _finish_node(state, {"last_error": ErrorCode.RUN_STEP_LIMIT_REACHED.value})
        finish = _finish_args(outcome.messages)
        rounds = state.get("clarification_rounds", 0)
        if (
            finish.needs_clarification
            and rounds == 0
            and state.get("run_kind", RunKind.PIPELINE) == RunKind.PIPELINE
        ):
            logger.info(
                "research.clarification_requested", questions=len(finish.needs_clarification)
            )
            return _finish_node(
                state,
                {
                    "clarification": finish.needs_clarification[:MAX_CLARIFICATION_QUESTIONS],
                    "clarification_rounds": rounds + 1,
                },
            )
        if finish.needs_clarification:
            logger.info("research.clarification_ignored")
        async with scope.session() as session:
            await _close(session, scope, finish)
        return _finish_node(state, {"stage": Stage.SCORING})

    return node


class _LoopEnd(StrEnum):
    FINISHED = "finished"
    STEP_LIMIT = "step_limit"
    EXA_LOST = "exa_lost"


@dataclass(frozen=True)
class _LoopOutcome:
    """How the research loop ended; ``messages`` are set only when it ``FINISHED``."""

    end: _LoopEnd
    messages: Sequence[AnyMessage] = ()


async def _research(
    scope: ResearchScope, redis: Redis, make_exa_client: ClientFactory, budget: ExaCallBudget
) -> _LoopOutcome:
    """Run the loop inside the Exa session.

    The step limit and a lost Exa (not another provider's failure) are caught inside the
    session, so they end it cleanly. Exa failing at connect, or before the loop saved anything,
    still raises ``UpstreamError``.
    """
    async with scope.session() as session:
        credentials = await get_key_for_use(session, scope.workspace_id, ProviderKind.EXA)
        model = await scope.gateway.chat_model(session, PURPOSE)
        seed = await _seed(session, scope)
        gates = await build_gate_context(scope.gateway, session, redis, scope.run_id)
    async with open_exa_tools(
        credentials.api_key, scope.run_id, redis, make_exa_client
    ) as exa_tools:
        capped = with_call_cap(
            exa_tools_for(Specialist.RESEARCHER.value, exa_tools), budget, limit_message=CAP_MESSAGE
        )
        exa = with_research_gate(
            capped,
            budget=budget,
            memory=CallMemory(redis, scope.run_id),
            context=with_kb_matches(gates, kb_lookup_for(scope)),
            load_knowledge=lambda: load_run_knowledge(scope),
            limit_message=CAP_MESSAGE,
        )
        loop = build_react_specialist(
            load_specialist_prompt(PROMPT),
            [*exa, *research_tools(scope)],
            model,
            step_limit=STEP_LIMIT,
            finish_tools={FINISH_RESEARCH},
            refusals=(GateRefusal,),
        )
        try:
            result = await loop.ainvoke({"messages": [HumanMessage(content=seed)]})
        except GraphRecursionError:
            return _LoopOutcome(_LoopEnd.STEP_LIMIT)
        except UpstreamError as exc:
            if not _is_exa_failure(exc) or not await _has_findings(scope):
                raise
            logger.warning("research.exa_lost", reason=(exc.meta or {}).get("reason"))
            return _LoopOutcome(_LoopEnd.EXA_LOST)
    return _LoopOutcome(_LoopEnd.FINISHED, tuple(result["messages"]))


def _is_exa_failure(exc: UpstreamError) -> bool:
    """Whether ``exc`` is Exa failing; the LLM gateway raises ``UpstreamError`` too."""
    return (exc.meta or {}).get("provider") == EXA_PROVIDER


async def _has_findings(scope: ResearchScope) -> bool:
    """Whether this run's snapshot holds a competitor or a research item."""
    async with scope.session() as session:
        snapshot = await open_run_snapshot(session, scope)
        saved = await research.get_snapshot(session, scope.workspace_id, snapshot.id)
    return bool(saved.items or saved.competitors)


async def _close_partial(state: MetisState, scope: ResearchScope) -> dict[str, Any]:
    """Close the snapshot with what was found, tell the user it is incomplete, go on to scoring."""
    get_stream_writer()(
        {
            "type": RunEventType.NOTICE.value,
            "code": NOTICE_PARTIAL_EXA_LOST,
            "text": NOTICE_PARTIAL_EXA_LOST_TEXT,
        }
    )
    async with scope.session() as session:
        await _close(session, scope, ResearchFinish(summary=EXA_LOST_SUMMARY))
    return _finish_node(state, {"stage": Stage.SCORING})


async def _exa_key_missing(scope: ResearchScope) -> bool:
    """Whether the workspace has no Exa key saved (presence only; no decryption)."""
    async with scope.session() as session:
        readiness = await key_readiness(session, scope.workspace_id, ProviderKind.EXA)
    return readiness is KeyReadiness.NOT_CONFIGURED


async def _already_closed(scope: ResearchScope) -> bool:
    """Whether this run's snapshot is already closed (research finished before a crash)."""
    async with scope.session() as session:
        latest = await research.latest_snapshot(session, scope.workspace_id, scope.idea_id)
    return latest is not None and latest.run_id == scope.run_id


async def _seed(session: AsyncSession, scope: ResearchScope) -> str:
    """What the model starts from: the idea, the brief, the user's answers, saved findings."""
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
    snapshot = await open_run_snapshot(session, scope)
    saved = await research.get_snapshot(session, scope.workspace_id, snapshot.id)
    if saved.items or saved.competitors:
        names = [c.name for c in saved.competitors]
        titles = [f"{i.kind.value}: {i.title}" for i in saved.items]
        parts.append(
            "Already saved in this run (do not save again):\n"
            + "\n".join(f"- {line}" for line in [*names, *titles])
        )
    return "\n\n".join(parts)


def _finish_args(messages: Sequence[AnyMessage]) -> ResearchFinish:
    """The arguments of the last ``finish_research`` call that ran, or an empty finish."""
    args = finished_call_args(messages, FINISH_RESEARCH)
    if args is not None:
        try:
            return ResearchFinish.model_validate(args)
        except ValidationError:
            logger.warning("research.finish_invalid")
    else:
        logger.warning("research.finished_without_output")
    return ResearchFinish()


async def _close(session: AsyncSession, scope: ResearchScope, finish: ResearchFinish) -> None:
    """Close the run's snapshot; say so in the summary when it has no competitor."""
    snapshot = await open_run_snapshot(session, scope)
    view = await research.get_snapshot(session, scope.workspace_id, snapshot.id)
    summary = finish.summary.strip() or NO_SUMMARY
    if not view.competitors and NO_COMPETITORS_NOTE not in summary:
        room = SUMMARY_LIMIT - len(NO_COMPETITORS_NOTE) - 1
        summary = f"{summary[:room]} {NO_COMPETITORS_NOTE}"
    await research.close_snapshot(session, scope.workspace_id, snapshot.id, summary[:SUMMARY_LIMIT])


def _finish_node(state: MetisState, update: dict[str, Any]) -> dict[str, Any]:
    get_stream_writer()(
        {"type": RunEventType.NODE_FINISHED.value, "node": Specialist.RESEARCHER.value}
    )
    return {**update, "step_count": state["step_count"] + 1}
