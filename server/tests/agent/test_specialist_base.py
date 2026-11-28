"""The shared tool-calling specialist loop, driven by a fake ``LLMProvider``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph

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


class _RunState(TypedDict, total=False):
    done: bool


async def test_a_non_resumable_loop_runs_inside_a_run_that_waits_for_each_checkpoint() -> None:
    """The run streams with ``durability="sync"``; a loop with no checkpointer must not wait
    for a save it never makes (it crashed with ``_put_checkpoint_fut``)."""
    model = FakeChat([_call_echo("hi"), AIMessage(content="done")])
    loop = build_react_specialist("p", [echo], model, resumable=False)

    async def node(_state: _RunState) -> _RunState:
        await loop.ainvoke({"messages": [HumanMessage(content="go")]})
        return {"done": True}

    graph = StateGraph(_RunState)
    graph.add_node("node", node)
    graph.add_edge(START, "node")
    graph.add_edge("node", END)
    run = graph.compile(checkpointer=InMemorySaver())

    chunks = [
        chunk
        async for chunk in run.astream(
            {}, {"configurable": {"thread_id": "t"}}, stream_mode="values", durability="sync"
        )
    ]

    assert chunks[-1] == {"done": True}
    assert len(model.seen) == 2


async def test_resumable_loop_interrupt_and_resume_passes_answer_to_tool() -> None:
    from langgraph.types import Command, interrupt

    @tool
    def ask(question: str) -> str:
        """Ask the user."""
        return str(interrupt({"question": question}))

    ask_call = {"name": "ask", "args": {"question": "lang?"}, "id": "c1"}
    model = FakeChat([AIMessage(content="", tool_calls=[ask_call]), AIMessage(content="got it")])
    loop = build_react_specialist("p", [ask], model, resumable=True)

    async def node(_state: _RunState) -> _RunState:
        await loop.ainvoke({"messages": [HumanMessage(content="go")]})
        return {"done": True}

    graph = StateGraph(_RunState)
    graph.add_node("node", node)
    graph.add_edge(START, "node")
    graph.add_edge("node", END)
    run = graph.compile(checkpointer=InMemorySaver())
    cfg: RunnableConfig = {"configurable": {"thread_id": "t-int"}}

    await run.ainvoke({}, cfg)
    result = await run.ainvoke(Command(resume="TypeScript"), cfg)

    assert result == {"done": True}
    assert len(model.seen) == 2
    assert any(
        isinstance(m, ToolMessage) and m.content == "TypeScript" for m in model.seen[1]
    )


async def test_skipping_non_resumable_loop_on_resume_keeps_later_checkpoint() -> None:
    from langgraph.types import Command, interrupt

    @tool
    def ask(question: str) -> str:
        """Ask the user."""
        return str(interrupt({"question": question}))

    draft_model = FakeChat([AIMessage(content="spec")])
    ask_call = {"name": "ask", "args": {"question": "lang?"}, "id": "c1"}
    hld_model = FakeChat([AIMessage(content="", tool_calls=[ask_call]), AIMessage(content="hld")])
    draft_loop = build_react_specialist("p", [], draft_model, resumable=False)
    hld_loop = build_react_specialist("p", [ask], hld_model, resumable=True)
    drafted = False

    async def node(_state: _RunState) -> _RunState:
        nonlocal drafted
        if not drafted:
            await invoke_loop(draft_loop, "draft")
            drafted = True
        await invoke_loop(hld_loop, "hld")
        return {"done": True}

    graph = StateGraph(_RunState)
    graph.add_node("node", node)
    graph.add_edge(START, "node")
    graph.add_edge("node", END)
    run = graph.compile(checkpointer=InMemorySaver())
    cfg: RunnableConfig = {"configurable": {"thread_id": "t-skip"}}

    await run.ainvoke({}, cfg, durability="sync")
    result = await run.ainvoke(Command(resume="TypeScript"), cfg, durability="sync")

    assert result == {"done": True}
    assert len(hld_model.seen) == 2
    assert any(
        isinstance(m, ToolMessage) and m.content == "TypeScript" for m in hld_model.seen[1]
    )
