"""The one LangGraph graph every run uses: a supervisor routing to seven specialists.

``build_graph`` compiles it with a checkpointer (``thread_id`` = run id). Specialists are
nodes passed in by name; the default is the stubs, and a later issue swaps in real ones, or
a test swaps in a node that calls ``ask_user``. Every specialist returns to the supervisor,
which ends the run when the stage has no specialist, a node set ``last_error``, or the step
budget is spent.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from metis.agent.specialists.stubs import SpecialistNode, stub_specialists
from metis.agent.state import MetisState
from metis.agent.supervisor import SUPERVISOR_NODE, Specialist, route, supervise

CompiledGraph = CompiledStateGraph[MetisState, None, MetisState, MetisState]


def build_graph(
    checkpointer: BaseCheckpointSaver[Any],
    *,
    specialists: Mapping[Specialist, SpecialistNode] | None = None,
) -> CompiledGraph:
    """The compiled graph; ``specialists`` replaces stub nodes by specialist."""
    nodes = {**stub_specialists(), **(specialists or {})}
    graph: StateGraph[MetisState, None, MetisState, MetisState] = StateGraph(MetisState)
    graph.add_node(SUPERVISOR_NODE, supervise)
    graph.add_edge(START, SUPERVISOR_NODE)
    graph.add_conditional_edges(SUPERVISOR_NODE, route)
    for specialist, node in nodes.items():
        # langgraph's overloads infer ``Never`` for a node held in a variable.
        graph.add_node(specialist.value, node)  # type: ignore[arg-type]
        graph.add_edge(specialist.value, SUPERVISOR_NODE)
    return graph.compile(checkpointer=checkpointer)
