"""Interrupts pause a run, and ``Command(resume=...)`` continues it from the checkpoint alone."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from metis.agent.checkpoint import open_checkpointer
from metis.agent.graph import build_graph
from metis.agent.state import MetisState
from metis.agent.supervisor import Specialist
from metis.agent.tools.ask_user import ask_user, request_approval
from metis.modules.ideas import Stage
from tests.agent.graph_helpers import (
    APP_DATABASE_URL,
    config_for,
    start_state,
    stream,
    visited_specialists,
)


async def _interviewer_that_asks(state: MetisState) -> dict[str, Any]:
    answer = await ask_user.ainvoke({"question": "Who pays for this?"})
    return {
        "stage": Stage.RESEARCHING,
        "summary": f"payer: {answer}",
        "step_count": state["step_count"] + 1,
    }


async def _integrator_that_asks(state: MetisState) -> dict[str, Any]:
    approved = await request_approval.ainvoke({"action": "create issues", "details": "12 issues"})
    return {
        "stage": Stage.EXPORTED if approved else Stage.PLANNING,
        "pending_approval": None if approved else {"action": "create issues"},
        "step_count": state["step_count"] + 1,
    }


ASKING = {Specialist.INTERVIEWER: _interviewer_that_asks}
APPROVING = {Specialist.INTEGRATOR: _integrator_that_asks}


async def test_ask_user_pauses_the_run_with_a_question(
    checkpointer: AsyncPostgresSaver,
) -> None:
    graph = build_graph(checkpointer, specialists=ASKING)
    state = start_state()

    trace = await stream(graph, state, config_for(state))

    assert trace.interrupts == [{"type": "question", "question": "Who pays for this?"}]
    snapshot = await graph.aget_state(config_for(state))
    assert snapshot.next == ("interviewer",)
    assert snapshot.values["stage"] == Stage.INTAKE


async def test_resume_continues_with_the_answer(checkpointer: AsyncPostgresSaver) -> None:
    graph = build_graph(checkpointer, specialists=ASKING)
    state = start_state()
    await stream(graph, state, config_for(state))

    trace = await stream(graph, Command(resume="developers"), config_for(state))

    assert visited_specialists(trace)[0] == "interviewer"
    final = (await graph.aget_state(config_for(state))).values
    assert final["summary"].startswith("payer: developers")
    assert final["stage"] == Stage.EXPORTED


async def test_a_fresh_graph_resumes_a_paused_run_from_the_checkpointer_alone(
    checkpointer: AsyncPostgresSaver,
) -> None:
    state = start_state()
    await stream(build_graph(checkpointer, specialists=ASKING), state, config_for(state))

    async with open_checkpointer(APP_DATABASE_URL) as other_process_saver:
        fresh = build_graph(other_process_saver, specialists=ASKING)
        await stream(fresh, Command(resume="teams"), config_for(state))
        final = (await fresh.aget_state(config_for(state))).values

    assert final["summary"].startswith("payer: teams")
    assert final["stage"] == Stage.EXPORTED


async def test_approval_pauses_before_an_external_write_and_resumes_on_yes(
    checkpointer: AsyncPostgresSaver,
) -> None:
    graph = build_graph(checkpointer, specialists=APPROVING)
    state = start_state(Stage.PLANNING)

    paused = await stream(graph, state, config_for(state))
    assert paused.interrupts == [
        {"type": "approval", "action": "create issues", "details": "12 issues"}
    ]
    assert (await graph.aget_state(config_for(state))).values["stage"] == Stage.PLANNING

    await stream(graph, Command(resume=True), config_for(state))
    assert (await graph.aget_state(config_for(state))).values["stage"] == Stage.EXPORTED
