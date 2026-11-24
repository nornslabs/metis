"""The supervisor: a pure function from the run's state to the next node.

It calls no LLM, database or module. ``STAGE_ROUTES`` is the one place that says which
specialist works on which stage; it covers every ``Stage``, so a new stage fails a test
until it is routed. A run ends when its stage has no specialist (``exported``), when a
node set ``last_error``, or when ``step_count`` reaches the budget's ``max_steps``.
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Any

from langgraph.graph import END

from metis.agent.state import MetisState
from metis.core.errors import ErrorCode
from metis.modules.ideas import RunKind, Stage

SUPERVISOR_NODE = "supervisor"


class Specialist(StrEnum):
    """The graph's specialist nodes."""

    INTERVIEWER = "interviewer"
    RESEARCHER = "researcher"
    SCORER = "scorer"
    ADVISOR = "advisor"
    ARCHITECT = "architect"
    PLANNER = "planner"
    INTEGRATOR = "integrator"


STAGE_ROUTES: MappingProxyType[Stage, Specialist | None] = MappingProxyType(
    {
        Stage.INTAKE: Specialist.INTERVIEWER,
        Stage.INTERVIEWING: Specialist.INTERVIEWER,
        Stage.RESEARCHING: Specialist.RESEARCHER,
        Stage.SCORING: Specialist.SCORER,
        Stage.ADVISING: Specialist.ADVISOR,
        Stage.SPEC_DRAFT: Specialist.ARCHITECT,
        Stage.SPEC_CONFIRMED: Specialist.PLANNER,
        Stage.PLANNING: Specialist.INTEGRATOR,
        Stage.EXPORTED: None,
    }
)


def supervise(state: MetisState) -> dict[str, Any]:
    """The supervisor node: ends the run with ``last_error`` once the step budget is spent."""
    if state["last_error"] is not None or STAGE_ROUTES[state["stage"]] is None:
        return {}
    if state["step_count"] >= state["budget"]["max_steps"]:
        return {"last_error": ErrorCode.RUN_STEP_LIMIT_REACHED.value}
    return {}


def route(state: MetisState) -> str:
    """The next node for ``state``: a specialist's name, or ``END``.

    A run whose Researcher skipped research (``research_skipped``) ends here too, with the
    stage left at ``researching`` so a later run picks the research up; so does a run the user
    stopped at the Advisor's decision (``advice_stopped``), with the stage left at ``advising``.

    Pending ``clarification`` questions (from the Researcher) go to the Interviewer whatever
    the stage; once it has asked them the stage routes back to the Researcher.
    """
    if state.get("continuation_prompt") and not state.get("continuation_done"):
        return Specialist.INTERVIEWER.value
    if state.get("refresh_complete"):
        return END
    if state.get("research_skipped"):
        if state.get("run_kind") == RunKind.MARKET_RECHECK:
            return Specialist.SCORER.value
        return END
    specialist = STAGE_ROUTES[state["stage"]]
    if state["last_error"] is not None or specialist is None or state.get("advice_stopped"):
        return END
    if state.get("clarification"):
        return Specialist.INTERVIEWER.value
    return specialist.value
