"""Stub specialists: each moves the stage forward and reports ``node_finished``.

Real specialists replace them one by one in later issues. The happy path visits every
specialist: after the Scorer's first pass the Advisor sends the run back to ``scoring``
(the allowed rescore transition), and the second pass goes on to ``spec_draft``. The
Advisor leaves ``ADVISED_MARKER`` in ``summary`` so the Scorer knows it has been.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Mapping
from typing import Any

from langgraph.config import get_stream_writer

from metis.agent.state import MetisState
from metis.agent.supervisor import Specialist
from metis.core.events import RunEventType
from metis.modules.ideas import Stage

ADVISED_MARKER = "advisor:done"

SpecialistNode = Callable[[MetisState], Coroutine[Any, Any, dict[str, Any]]]


def stub_specialists() -> Mapping[Specialist, SpecialistNode]:
    """One stub node per specialist."""
    return {specialist: _stub(specialist) for specialist in Specialist}


def _stub(specialist: Specialist) -> SpecialistNode:
    async def node(state: MetisState) -> dict[str, Any]:
        update = _ADVANCE[specialist](state)
        get_stream_writer()({"type": RunEventType.NODE_FINISHED.value, "node": specialist.value})
        return {**update, "step_count": state["step_count"] + 1}

    return node


def _interviewer(state: MetisState) -> dict[str, Any]:
    nxt = Stage.INTERVIEWING if state["stage"] == Stage.INTAKE else Stage.RESEARCHING
    return {"stage": nxt}


def _scorer(state: MetisState) -> dict[str, Any]:
    advised = ADVISED_MARKER in state["summary"]
    return {"stage": Stage.SPEC_DRAFT if advised else Stage.ADVISING}


def _advisor(state: MetisState) -> dict[str, Any]:
    return {"stage": Stage.SCORING, "summary": f"{state['summary']} {ADVISED_MARKER}".strip()}


_ADVANCE: Mapping[Specialist, Callable[[MetisState], dict[str, Any]]] = {
    Specialist.INTERVIEWER: _interviewer,
    Specialist.RESEARCHER: lambda _: {"stage": Stage.SCORING},
    Specialist.SCORER: _scorer,
    Specialist.ADVISOR: _advisor,
    Specialist.ARCHITECT: lambda _: {"stage": Stage.SPEC_CONFIRMED},
    Specialist.PLANNER: lambda _: {"stage": Stage.PLANNING},
    Specialist.INTEGRATOR: lambda _: {"stage": Stage.EXPORTED},
}
