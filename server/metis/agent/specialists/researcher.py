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
from typing import Any
from uuid import UUID

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.config import get_stream_writer
from langgraph.errors import GraphRecursionError
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from metis.agent.llm import LLMGateway
from metis.agent.prompts import load_prompt
from metis.agent.specialists.base import build_react_specialist, finished_call_args
from metis.agent.specialists.stubs import SpecialistNode
from metis.agent.state import MetisState
from metis.agent.supervisor import Specialist
from metis.agent.tools.exa import ExaCallBudget, exa_tools_for, open_exa_tools, with_call_cap
from metis.agent.tools.research_kb import (
    FINISH_RESEARCH,
    MAX_CLARIFICATION_QUESTIONS,
    ResearchFinish,
    ResearchScope,
    SessionOpener,
    open_run_snapshot,
    research_tools,
)
from metis.core.errors import ErrorCode
from metis.core.events import RunEventType
from metis.core.logging import get_logger
from metis.helpers.http import ClientFactory
from metis.modules import ideas, research
from metis.modules.ideas import Stage
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
) -> SpecialistNode:
    """The Researcher node for one run."""

    async def node(state: MetisState) -> dict[str, Any]:
        scope = ResearchScope(
            workspace_id=UUID(state["workspace_id"]),
            idea_id=UUID(state["idea_id"]),
            run_id=UUID(state["run_id"]),
            open_session=open_session,
            gateway=gateway,
        )
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
        try:
            messages = await _research(scope, redis, make_exa_client, budget)
        except GraphRecursionError:
            logger.warning("research.step_limit_reached")
            return _finish_node(state, {"last_error": ErrorCode.RUN_STEP_LIMIT_REACHED.value})
        finish = _finish_args(messages)
        rounds = state.get("clarification_rounds", 0)
        if finish.needs_clarification and rounds == 0:
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


async def _research(
    scope: ResearchScope, redis: Redis, make_exa_client: ClientFactory, budget: ExaCallBudget
) -> list[AnyMessage]:
    async with scope.session() as session:
        credentials = await get_key_for_use(session, scope.workspace_id, ProviderKind.EXA)
        model = await scope.gateway.chat_model(session, PURPOSE)
        seed = await _seed(session, scope)
    async with open_exa_tools(
        credentials.api_key, scope.run_id, redis, make_exa_client
    ) as exa_tools:
        exa = with_call_cap(
            exa_tools_for(Specialist.RESEARCHER.value, exa_tools), budget, limit_message=CAP_MESSAGE
        )
        loop = build_react_specialist(
            load_prompt(PROMPT),
            [*exa, *research_tools(scope)],
            model,
            step_limit=STEP_LIMIT,
            finish_tools={FINISH_RESEARCH},
        )
        result = await loop.ainvoke({"messages": [HumanMessage(content=seed)]})
    return list(result["messages"])


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
