"""The shared tool-calling specialist loop, driven by a fake ``LLMProvider``."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError

from metis.agent.specialists.base import (
    ToolInvocationLimitError,
    build_react_specialist,
    invoke_loop,
)
from metis.core.ports import LLMProvider, ToolDefinition
from metis.helpers.dto import JsonList


class FakeChat:
    """A scripted ``LLMProvider``: replies in order, repeating the last one."""

    def __init__(self, replies: Sequence[AIMessage]) -> None:
        self._replies = list(replies)
        self.seen: list[Sequence[BaseMessage]] = []
        self.bound: Sequence[ToolDefinition] = ()

    def bind_tools(self, tools: Sequence[ToolDefinition]) -> LLMProvider:
        self.bound = tools
        return self

    async def ainvoke(
        self, messages: Sequence[BaseMessage], config: RunnableConfig | None = None
    ) -> AIMessage:
        self.seen.append(messages)
        reply = self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]
        return reply.model_copy(deep=True)  # a fresh object: message ids are assigned in place

    async def aclose(self) -> None:
        return None


@tool
def echo(text: str) -> str:
    """Return the text unchanged."""
    return text


def _call_echo(text: str, call_id: str = "call-1") -> AIMessage:
    call = {"name": "echo", "args": {"text": text}, "id": call_id}
    return AIMessage(content="", tool_calls=[call])


async def test_model_calls_a_tool_then_answers() -> None:
    model = FakeChat([_call_echo("hi"), AIMessage(content="done")])
    agent = build_react_specialist("You are a tester.", [echo], model)

    result = await agent.ainvoke({"messages": [HumanMessage(content="go")]})

    messages = result["messages"]
    assert [type(m) for m in messages] == [HumanMessage, AIMessage, ToolMessage, AIMessage]
    assert messages[2].content == "hi"
    assert messages[-1].content == "done"
    assert model.seen[0][0].content == "You are a tester."
    assert model.bound == [echo]


async def test_a_loop_that_never_settles_stops_at_the_step_limit() -> None:
    model = FakeChat([_call_echo("again")])
    agent = build_react_specialist("p", [echo], model, step_limit=5)

    with pytest.raises(GraphRecursionError):
        await agent.ainvoke({"messages": [HumanMessage(content="go")]})


async def test_without_tools_the_model_answers_once() -> None:
    model = FakeChat([AIMessage(content="plain")])
    agent = build_react_specialist("p", [], model)

    result = await agent.ainvoke({"messages": [HumanMessage(content="go")]})

    assert result["messages"][-1].content == "plain"


async def test_a_finishing_tool_ends_the_loop_without_another_model_call() -> None:
    model = FakeChat([_call_echo("final"), AIMessage(content="never sent")])
    agent = build_react_specialist("p", [echo], model, finish_tools={"echo"})

    result = await agent.ainvoke({"messages": [HumanMessage(content="go")]})

    messages = result["messages"]
    assert [type(m) for m in messages] == [HumanMessage, AIMessage, ToolMessage]
    assert len(model.seen) == 1


async def test_three_consecutive_tool_invocation_errors_stop_the_loop() -> None:
    bad = AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": 123}, "id": "c1"}])
    model = FakeChat([bad])
    agent = build_react_specialist("p", [echo], model, step_limit=20)

    with pytest.raises(ToolInvocationLimitError):
        await agent.ainvoke({"messages": [HumanMessage(content="go")]})

    assert len(model.seen) == 3


async def test_a_successful_tool_call_resets_the_tool_invocation_error_count() -> None:
    bad = AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": 123}, "id": "c1"}])
    model = FakeChat([bad, bad, _call_echo("ok", "c2"), bad, bad, AIMessage(content="done")])
    agent = build_react_specialist("p", [echo], model, step_limit=20)

    result = await agent.ainvoke({"messages": [HumanMessage(content="go")]})

    assert result["messages"][-1].content == "done"


async def test_invoke_loop_returns_true_on_tool_invocation_limit() -> None:
    bad = AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": 123}, "id": "c1"}])
    model = FakeChat([bad])
    agent = build_react_specialist("p", [echo], model, step_limit=20)

    assert await invoke_loop(agent, "go") is True


def test_json_list_accepts_stringified_json_and_rejects_malformed_json() -> None:
    from pydantic import BaseModel, ValidationError

    class Args(BaseModel):
        items: JsonList[str]

    assert Args.model_validate({"items": '["a", "b"]'}).items == ["a", "b"]
    with pytest.raises(ValidationError):
        Args.model_validate({"items": '["a", unquoted]'})


async def test_non_resumable_specialist_runs_inside_sync_durability_parent() -> None:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, MessagesState, StateGraph

    model = FakeChat([AIMessage(content="ok")])
    sub = build_react_specialist("p", [], model, resumable=False)

    parent = StateGraph(MessagesState)

    async def call_sub(state: MessagesState) -> dict[str, list[BaseMessage]]:
        return dict(await sub.ainvoke({"messages": state["messages"]}))

    parent.add_node("sub", call_sub)
    parent.add_edge(START, "sub")
    parent.add_edge("sub", END)
    compiled = parent.compile(checkpointer=InMemorySaver())

    chunks = [
        chunk
        async for chunk in compiled.astream(
            {"messages": [HumanMessage(content="go")]},
            {"configurable": {"thread_id": "t-sync"}},
            durability="sync",
            subgraphs=True,
        )
    ]
    assert chunks
