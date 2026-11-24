"""The Planner: turns the confirmed spec into phases and tasks, with the user reviewing the phases.

At ``spec_confirmed`` it runs a tool-calling loop (``build_react_specialist``) over the planner
prompt, ``propose_phases`` and ``save_plan``, on the run's ``plan`` chat model, seeded with the
idea, its interview, the research and the confirmed spec. ``propose_phases`` pauses on a
``phase_review`` interrupt; the user's reviewed list is the only phase list the plan may use.
``save_plan`` stores the plan as a draft for the confirmed spec version. The node then moves the
run to ``planning``. A plan that cannot be saved (two refused ``save_plan`` calls, or none) fails
the run with ``plan.invalid_submission``; no confirmed spec fails it with ``spec.not_found``.

The node is safe to re-run: it does only reads before the loop, the loop continues from its
checkpoint after the interrupt (the model is not called again), and when the plan for the spec
version already exists (a crash re-run, or an earlier run's plan) it makes no model call.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_mcp_adapters.sessions import McpHttpClientFactory
from langgraph.config import get_stream_writer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from metis.agent.llm import LLMGateway
from metis.agent.prompts import load_prompt
from metis.agent.specialists.base import build_react_specialist, invoke_loop
from metis.agent.specialists.idea_context import idea_seed_parts
from metis.agent.specialists.stubs import SpecialistNode
from metis.agent.state import MetisState
from metis.agent.supervisor import Specialist
from metis.agent.tools.mcp import McpRunContext, load_optional_mcp_tools
from metis.agent.tools.mcp_policy import PLANNER_POLICY
from metis.agent.tools.planning import SAVE_PLAN, PlanLedger, PlanRefused, planning_tools
from metis.agent.tools.research_kb import ResearchScope, SessionOpener
from metis.agent.tools.scoring import SourceBook
from metis.core.errors import ErrorCode, PlanNotFoundError
from metis.core.events import RunEventType
from metis.core.logging import get_logger
from metis.helpers.http import ClientFactory
from metis.modules import ideas, planning
from metis.modules.ideas import SpecVersion, Stage

PROMPT = "planner"
PURPOSE = "plan"
# Graph supersteps between two pauses: the phase proposal, then the plan with room for one
# refused attempt; each resume starts counting again.
STEP_LIMIT = 20

logger = get_logger(__name__)


def build_planner(
    gateway: LLMGateway,
    open_session: SessionOpener,
    redis: Redis,
    make_client: ClientFactory,
    mcp_http_client: McpHttpClientFactory | None = None,
) -> SpecialistNode:
    """The Planner node for one run. Linear's read tools join its loop when Linear is connected."""

    async def node(state: MetisState) -> dict[str, Any]:
        scope = ResearchScope(
            workspace_id=UUID(state["workspace_id"]),
            idea_id=UUID(state["idea_id"]),
            run_id=UUID(state["run_id"]),
            open_session=open_session,
            gateway=gateway,
        )
        async with scope.session() as session:
            overview = await ideas.get_spec_overview(session, scope.workspace_id, scope.idea_id)
            spec = overview.confirmed
            if spec is None:
                logger.warning("plan.no_confirmed_spec")
                return _finish_node(state, {"last_error": ErrorCode.SPEC_NOT_FOUND.value})
            if await _has_plan(session, scope, spec):
                return _finish_node(state, {"stage": Stage.PLANNING})
        mcp = McpRunContext(
            workspace_id=scope.workspace_id,
            run_id=scope.run_id,
            open_session=open_session,
            redis=redis,
            make_client=make_client,
            mcp_http_client=mcp_http_client,
            specialist=Specialist.PLANNER.value,
        )
        failure = await _plan(scope, spec, mcp)
        if failure is not None:
            return _finish_node(state, {"last_error": failure})
        return _finish_node(state, {"stage": Stage.PLANNING})

    return node


async def _has_plan(session: AsyncSession, scope: ResearchScope, spec: SpecVersion) -> bool:
    try:
        await planning.get_plan(session, scope.workspace_id, scope.idea_id, spec.id)
    except PlanNotFoundError:
        return False
    return True


async def _plan(scope: ResearchScope, spec: SpecVersion, mcp: McpRunContext) -> str | None:
    """Run the loop; ``None`` when a plan was saved, else the error code to fail the run with."""
    ledger = PlanLedger()
    async with scope.session() as session:
        model = await scope.gateway.chat_model(session, PURPOSE)
        seed = await _seed(session, scope, spec)
    linear_tools = await load_optional_mcp_tools(mcp, PLANNER_POLICY)
    loop = build_react_specialist(
        load_prompt(PROMPT),
        [*linear_tools, *planning_tools(scope, ledger, spec.id)],
        model,
        step_limit=STEP_LIMIT,
        finish_tools={SAVE_PLAN},
        refusals=(PlanRefused,),
    )
    if not await invoke_loop(loop, seed):
        logger.warning("plan.step_limit_reached")
        return ErrorCode.RUN_STEP_LIMIT_REACHED.value
    if ledger.saved is None:
        logger.warning("plan.no_valid_plan", refusals=ledger.refusals)
        return ErrorCode.PLAN_INVALID_SUBMISSION.value
    return None


async def _seed(session: AsyncSession, scope: ResearchScope, spec: SpecVersion) -> str:
    """What the model starts from: the idea, interview, research and the confirmed spec."""
    parts = await idea_seed_parts(session, scope, SourceBook())
    idea = await ideas.get_idea(session, scope.workspace_id, scope.idea_id)
    kind = idea.kind.value if idea.kind else "unknown"
    parts.append(f"Idea kind: {kind}.")
    parts.append(f"Confirmed spec (version {spec.number}):\n{spec.content_md}")
    return "\n\n".join(parts)


def _finish_node(state: MetisState, update: dict[str, Any]) -> dict[str, Any]:
    get_stream_writer()(
        {"type": RunEventType.NODE_FINISHED.value, "node": Specialist.PLANNER.value}
    )
    return {**update, "step_count": state["step_count"] + 1}
