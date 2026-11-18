"""The Interviewer: an adaptive interview about the idea, then a brief for research.

At ``intake`` it only moves the run to ``interviewing`` (no model call). At
``interviewing`` it runs a tool-calling loop (``build_react_specialist``) over the
interviewer prompt, the four interview tools and the run's ``interview`` chat model,
seeded with the idea's title and text; ``finish_interview`` ends the loop. The loop pauses
on ``ask_user``; the node re-runs
from its start on resume and the subgraph continues from its checkpoint, so the node does
nothing with side effects before it. When the loop ends the node stores the brief (the
model's ``finish_interview`` findings + coverage from the saved turns) and moves the run to
``researching``. It never writes ``ideas.stage``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.errors import GraphRecursionError
from pydantic import ValidationError

from metis.agent.llm import LLMGateway
from metis.agent.prompts import load_prompt
from metis.agent.specialists.base import build_react_specialist
from metis.agent.specialists.stubs import SpecialistNode
from metis.agent.state import MetisState
from metis.agent.supervisor import Specialist
from metis.agent.tools.interview import (
    FINISH_INTERVIEW,
    InterviewScope,
    SessionOpener,
    interview_tools,
)
from metis.core.errors import ErrorCode
from metis.core.events import RunEventType
from metis.core.logging import get_logger
from metis.modules import ideas
from metis.modules.ideas import InterviewFindings, Stage

PROMPT = "interviewer"
PURPOSE = "interview"
# Graph supersteps between two pauses (a model call and its tool calls are two); each
# resume starts counting again. The question cap is enforced by the tools, not by this.
STEP_LIMIT = 40

logger = get_logger(__name__)


def build_interviewer(gateway: LLMGateway, open_session: SessionOpener) -> SpecialistNode:
    """The Interviewer node for one run: ``gateway`` gives its model, ``open_session`` its DB."""

    async def node(state: MetisState) -> dict[str, Any]:
        if state["stage"] == Stage.INTAKE:
            return _finish_node(state, {"stage": Stage.INTERVIEWING})
        scope = InterviewScope(
            workspace_id=UUID(state["workspace_id"]),
            idea_id=UUID(state["idea_id"]),
            run_id=UUID(state["run_id"]),
            open_session=open_session,
        )
        try:
            messages = await _interview(gateway, scope)
        except GraphRecursionError:
            logger.warning("interview.step_limit_reached")
            return _finish_node(state, {"last_error": ErrorCode.RUN_STEP_LIMIT_REACHED.value})
        async with scope.session() as session:
            brief = await ideas.finish_interview(
                session, scope.workspace_id, scope.idea_id, scope.run_id, _findings(messages)
            )
        logger.info("interview.finished", ended_by=brief.ended_by.value)
        return _finish_node(state, {"stage": Stage.RESEARCHING})

    return node


async def _interview(gateway: LLMGateway, scope: InterviewScope) -> list[AnyMessage]:
    async with scope.session() as session:
        idea = await ideas.get_idea(session, scope.workspace_id, scope.idea_id)
        model = await gateway.chat_model(session, PURPOSE)
    loop = build_react_specialist(
        load_prompt(PROMPT),
        interview_tools(scope),
        model,
        step_limit=STEP_LIMIT,
        finish_tools={FINISH_INTERVIEW},
    )
    seed = HumanMessage(content=f"Idea title: {idea.title}\n\nIdea text:\n{idea.raw_text}")
    result = await loop.ainvoke({"messages": [seed]})
    return list(result["messages"])


def _findings(messages: Sequence[AnyMessage]) -> InterviewFindings:
    """The arguments of the last ``finish_interview`` call that ran, or empty findings."""
    finished = {
        m.tool_call_id
        for m in messages
        if isinstance(m, ToolMessage) and m.name == FINISH_INTERVIEW and m.status == "success"
    }
    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue
        for call in reversed(message.tool_calls):
            if call["name"] == FINISH_INTERVIEW and call["id"] in finished:
                try:
                    return InterviewFindings.model_validate(call["args"])
                except ValidationError:
                    break
    logger.warning("interview.finished_without_findings")
    return InterviewFindings()


def _finish_node(state: MetisState, update: dict[str, Any]) -> dict[str, Any]:
    get_stream_writer()(
        {"type": RunEventType.NODE_FINISHED.value, "node": Specialist.INTERVIEWER.value}
    )
    return {**update, "step_count": state["step_count"] + 1}
