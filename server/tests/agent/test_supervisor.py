"""The supervisor routes every stage, and ends a run that has spent its step budget."""

from __future__ import annotations

import pytest
from langgraph.graph import END

from metis.agent.supervisor import STAGE_ROUTES, Specialist, route, supervise
from metis.core.errors import ErrorCode
from metis.modules.ideas import Stage
from tests.agent.graph_helpers import start_state

EXPECTED_ROUTES = {
    Stage.INTAKE: "interviewer",
    Stage.INTERVIEWING: "interviewer",
    Stage.RESEARCHING: "researcher",
    Stage.SCORING: "scorer",
    Stage.ADVISING: "advisor",
    Stage.SPEC_DRAFT: "architect",
    Stage.SPEC_CONFIRMED: "planner",
    Stage.PLANNING: "integrator",
    Stage.EXPORTED: END,
}


@pytest.mark.parametrize("stage", list(Stage))
def test_every_stage_routes_to_its_specialist_or_ends(stage: Stage) -> None:
    assert route(start_state(stage)) == EXPECTED_ROUTES[stage]


def test_every_specialist_has_a_stage() -> None:
    assert {s for s in STAGE_ROUTES.values() if s is not None} == set(Specialist)


def test_run_ends_with_step_limit_error_once_the_budget_is_spent() -> None:
    state = {**start_state(Stage.RESEARCHING, max_steps=3), "step_count": 3}

    update = supervise(state)

    assert update == {"last_error": ErrorCode.RUN_STEP_LIMIT_REACHED.value}
    assert route({**state, **update}) == END


def test_run_under_budget_keeps_going() -> None:
    state = {**start_state(Stage.RESEARCHING, max_steps=3), "step_count": 2}

    assert supervise(state) == {}
    assert route(state) == "researcher"


def test_a_finished_run_is_not_reported_as_over_budget() -> None:
    state = {**start_state(Stage.EXPORTED, max_steps=3), "step_count": 3}

    assert supervise(state) == {}


def test_pending_clarification_routes_to_the_interviewer_whatever_the_stage() -> None:
    state = {**start_state(Stage.RESEARCHING), "clarification": ["Which country?"]}

    assert route(state) == Specialist.INTERVIEWER.value


def test_a_run_the_user_stopped_at_the_advice_ends_with_the_stage_left_at_advising() -> None:
    state = {**start_state(Stage.ADVISING), "advice_stopped": True}

    assert route(state) == END
