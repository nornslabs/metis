"""The shared tool-calling specialist loop, driven by a fake ``LLMProvider``."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError

from metis.agent.specialists.base import build_react_specialist
from metis.core.ports import LLMProvider, ToolDefinition


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
