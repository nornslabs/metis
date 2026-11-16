"""The compiled graph: stage routing, step limit, and the checkpointer it runs on."""

from __future__ import annotations

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from metis.agent.graph import build_graph
from metis.core.errors import ErrorCode
from metis.modules.ideas import Stage
from tests.agent.graph_helpers import config_for, start_state, stream, visited_specialists

FULL_RUN = [
    "interviewer",
    "interviewer",
    "researcher",
    "scorer",
    "advisor",
    "scorer",
    "architect",
    "planner",
    "integrator",
]


async def test_stub_run_goes_through_every_stage_in_order(
    checkpointer: AsyncPostgresSaver,
) -> None:
    graph = build_graph(checkpointer)
    state = start_state()

    trace = await stream(graph, state, config_for(state))

    assert visited_specialists(trace) == FULL_RUN
    final = (await graph.aget_state(config_for(state))).values
    assert final["stage"] == Stage.EXPORTED
    assert final["last_error"] is None
    assert final["step_count"] == len(FULL_RUN)


async def test_each_specialist_reports_node_finished(checkpointer: AsyncPostgresSaver) -> None:
    graph = build_graph(checkpointer)
    state = start_state()

    trace = await stream(graph, state, config_for(state))

    assert [e["node"] for e in trace.events] == FULL_RUN
    assert {e["type"] for e in trace.events} == {"node_finished"}


async def test_run_stops_with_step_limit_error_when_max_steps_is_hit(
    checkpointer: AsyncPostgresSaver,
) -> None:
    graph = build_graph(checkpointer)
    state = start_state(max_steps=4)

    trace = await stream(graph, state, config_for(state))

    assert visited_specialists(trace) == FULL_RUN[:4]
    final = (await graph.aget_state(config_for(state))).values
    assert final["last_error"] == ErrorCode.RUN_STEP_LIMIT_REACHED.value
    assert final["stage"] != Stage.EXPORTED


async def test_run_with_exactly_enough_steps_completes(
    checkpointer: AsyncPostgresSaver,
) -> None:
    graph = build_graph(checkpointer)
    state = start_state(max_steps=len(FULL_RUN))

    await stream(graph, state, config_for(state))

    final = (await graph.aget_state(config_for(state))).values
    assert final["stage"] == Stage.EXPORTED
    assert final["last_error"] is None
