"""The shared builder for tool-calling specialists (ReAct-style loop).

A specialist is a prompt, a tool allow-list, the gateway's chat model and a step limit.
The loop is: the model replies; if it asked for tools they run and it replies again; it
ends when a reply asks for none, or right after a ``finish_tools`` tool ran successfully
(a specialist's structured output). The model only ever sees the tools passed here, and the
step limit (graph supersteps, one model call plus its tool calls) stops a loop that never
settles by raising ``GraphRecursionError``. It counts per invocation: a loop that pauses on
``interrupt()`` and is resumed starts counting again.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph._internal._constants import CONFIG_KEY_DURABILITY
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.prebuilt.tool_node import ToolInvocationError

from metis.core.ports import LLMProvider

AGENT_NODE = "agent"
TOOLS_NODE = "tools"
DEFAULT_STEP_LIMIT = 12
NO_SAVE_DURABILITY = "exit"


def build_react_specialist(
    prompt: str,
    tools: Sequence[BaseTool],
    model: LLMProvider,
    *,
    step_limit: int = DEFAULT_STEP_LIMIT,
    finish_tools: Collection[str] = (),
    refusals: tuple[type[Exception], ...] = (),
    resumable: bool = True,
) -> Any:
    """A compiled subgraph over ``MessagesState``; invoke it with ``{"messages": [...]}``.

    A tool may refuse a call by raising one of ``refusals``: the model gets the message back as
    an error result (which never ends the loop) and may try again. Any other tool error fails
    the run.

    A loop that can pause on ``interrupt()`` must be ``resumable`` (it keeps its own checkpoint
    under the parent's). The checkpoint of a subgraph is keyed by the order of the calls in its
    node, so a node that runs several loops, some of which a re-run skips, makes every loop that
    cannot pause ``resumable=False``: it then starts clean each time and never reuses another
    loop's finished checkpoint.
    """
    bound = model.bind_tools(tools) if tools else model

    async def call_model(state: MessagesState) -> dict[str, Any]:
        reply = await bound.ainvoke([SystemMessage(content=prompt), *state["messages"]])
        return {"messages": [reply]}

    graph = StateGraph(MessagesState)
    graph.add_node(AGENT_NODE, call_model)
    graph.add_edge(START, AGENT_NODE)
    if tools:
        handled: tuple[type[Exception], ...] = (ToolInvocationError, *refusals)
        graph.add_node(TOOLS_NODE, ToolNode(list(tools), handle_tool_errors=handled))
        graph.add_conditional_edges(AGENT_NODE, tools_condition, {"tools": TOOLS_NODE, END: END})
        graph.add_conditional_edges(TOOLS_NODE, _after_tools(frozenset(finish_tools)))
    else:
        graph.add_edge(AGENT_NODE, END)
    if resumable:
        return graph.compile().with_config({"recursion_limit": step_limit})
    # No checkpointer, so no save to wait for: pin the durability, or the loop inherits the
    # run's ``sync`` from the parent config and waits for a save that never happens.
    return graph.compile(checkpointer=False).with_config(
        {"recursion_limit": step_limit, "configurable": {CONFIG_KEY_DURABILITY: NO_SAVE_DURABILITY}}
    )


async def invoke_loop(loop: Any, seed: str) -> bool:
    """Run ``loop`` on ``seed``; ``False`` when it hit its step limit.

    The limit is caught here so a caller can call this inside an Exa session:
    ``open_mcp_session`` turns any exception that leaves its block into ``UpstreamError``,
    which would hide ``GraphRecursionError``.
    """
    try:
        await loop.ainvoke({"messages": [HumanMessage(content=seed)]})
    except GraphRecursionError:
        return False
    return True


def _after_tools(finish_tools: frozenset[str]) -> Any:
    """Route after a tool step: ``END`` when a finishing tool just succeeded, else the model."""

    def route(state: MessagesState) -> str:
        for message in reversed(state["messages"]):
            if not isinstance(message, ToolMessage):
                break
            if message.name in finish_tools and message.status == "success":
                return END
        return AGENT_NODE

    return route


def finished_call_args(messages: Sequence[AnyMessage], tool_name: str) -> dict[str, Any] | None:
    """The arguments of the last ``tool_name`` call that ran successfully, or ``None``."""
    finished = {
        m.tool_call_id
        for m in messages
        if isinstance(m, ToolMessage) and m.name == tool_name and m.status == "success"
    }
    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue
        for call in reversed(message.tool_calls):
            if call["name"] == tool_name and call["id"] in finished:
                return dict(call["args"])
    return None
