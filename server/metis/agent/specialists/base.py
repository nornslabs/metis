"""The shared builder for tool-calling specialists (ReAct-style loop).

A specialist is a prompt, a tool allow-list, the gateway's chat model and a step limit.
The loop is: the model replies; if it asked for tools they run and it replies again; it
ends when a reply asks for none. The model only ever sees the tools passed here, and the
step limit (graph supersteps, one model call plus its tool calls) stops a loop that never
settles by raising ``GraphRecursionError``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from metis.core.ports import LLMProvider

AGENT_NODE = "agent"
TOOLS_NODE = "tools"
DEFAULT_STEP_LIMIT = 12


def build_react_specialist(
    prompt: str,
    tools: Sequence[BaseTool],
    model: LLMProvider,
    *,
    step_limit: int = DEFAULT_STEP_LIMIT,
) -> Any:
    """A compiled subgraph over ``MessagesState``; invoke it with ``{"messages": [...]}``."""
    bound = model.bind_tools(tools) if tools else model

    async def call_model(state: MessagesState) -> dict[str, Any]:
        reply = await bound.ainvoke([SystemMessage(content=prompt), *state["messages"]])
        return {"messages": [reply]}

    graph = StateGraph(MessagesState)
    graph.add_node(AGENT_NODE, call_model)
    graph.add_edge(START, AGENT_NODE)
    if tools:
        graph.add_node(TOOLS_NODE, ToolNode(list(tools)))
        graph.add_conditional_edges(AGENT_NODE, tools_condition, {"tools": TOOLS_NODE, END: END})
        graph.add_edge(TOOLS_NODE, AGENT_NODE)
    else:
        graph.add_edge(AGENT_NODE, END)
    return graph.compile().with_config({"recursion_limit": step_limit})
