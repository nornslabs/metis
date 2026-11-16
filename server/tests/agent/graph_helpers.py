"""Helpers for graph tests: a run's starting state and the events a run streams."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from sqlalchemy.engine import make_url

from metis.agent.graph import CompiledGraph
from metis.agent.state import MetisState, initial_state
from metis.modules.ideas import Stage
from tests.helpers.auth import APP_ROLE, DATABASE_URL

MAX_STEPS = 50
APP_DATABASE_URL = (
    make_url(DATABASE_URL)
    .set(username=APP_ROLE, password=APP_ROLE)
    .render_as_string(hide_password=False)
)


def start_state(stage: Stage = Stage.INTAKE, max_steps: int = MAX_STEPS) -> MetisState:
    return initial_state(
        run_id=uuid4(), workspace_id=uuid4(), idea_id=uuid4(), stage=stage, max_steps=max_steps
    )


def config_for(state: MetisState) -> RunnableConfig:
    """The checkpoint thread of a run: its run id."""
    return {"configurable": {"thread_id": state["run_id"]}}


@dataclass
class RunTrace:
    """What one ``run`` or ``resume`` call streamed."""

    nodes: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    interrupts: list[Any] = field(default_factory=list)


async def stream(
    graph: CompiledGraph, payload: MetisState | Command[Any], config: RunnableConfig
) -> RunTrace:
    """Drive the graph until it ends or pauses, collecting visited nodes and events."""
    trace = RunTrace()
    async for mode, chunk in graph.astream(payload, config, stream_mode=["updates", "custom"]):
        if mode == "custom":
            trace.events.append(chunk)
            continue
        for node, update in chunk.items():
            if node == "__interrupt__":
                trace.interrupts.extend(item.value for item in update)
            else:
                trace.nodes.append(node)
    return trace


def visited_specialists(trace: RunTrace) -> Sequence[str]:
    return [node for node in trace.nodes if node != "supervisor"]
