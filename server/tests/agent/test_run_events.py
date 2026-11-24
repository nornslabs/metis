"""What a run publishes while a model streams: batched ``token`` events and ``tool_call`` events.

Seam: the ``run_graph`` job with a node that calls a fake streaming chat model, read back from
the run's Redis stream.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.state import MetisState
from metis.agent.supervisor import Specialist
from metis.core.events import RunEvent, RunEventType
from metis.modules.ideas import Stage
from tests.agent.run_job_helpers import events_of, job_ctx, queued_run, run_job, run_row

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

WORDS = [f"word{i}" for i in range(40)]


def _talking_interviewer(reply: AIMessage) -> Any:
    model = GenericFakeChatModel(messages=iter([reply]))

    async def node(state: MetisState) -> dict[str, Any]:
        await model.ainvoke("hello")
        return {"stage": Stage.RESEARCHING, "step_count": state["step_count"] + 1}

    return node


class _ToolCallingModel(BaseChatModel):
    """Streams one tool call the way providers do: the name first, the arguments after."""

    @property
    def _llm_type(self) -> str:
        return "tool-calling-fake"

    def _generate(self, messages: list[BaseMessage], **_: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=""))])

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        pieces = [
            {"name": "fake_tool", "args": '{"query": ', "id": "c1", "index": 0},
            {"name": None, "args": '"private plan"}', "id": None, "index": 0},
        ]
        for piece in pieces:
            yield ChatGenerationChunk(
                message=AIMessageChunk(content="", tool_call_chunks=[piece])  # type: ignore[list-item]
            )


def _tool_calling_interviewer() -> Any:
    model = _ToolCallingModel()

    async def node(state: MetisState) -> dict[str, Any]:
        await model.ainvoke("hello")
        return {"stage": Stage.RESEARCHING, "step_count": state["step_count"] + 1}

    return node


def _of(events: list[RunEvent], kind: RunEventType) -> list[RunEvent]:
    return [e for e in events if e.type is kind]


async def test_streamed_text_arrives_as_batched_token_events_in_order(
    engine: AsyncEngine,
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
) -> None:
    reply = AIMessage(content=" ".join(WORDS))
    ctx = job_ctx(redis, app_sessions, {Specialist.INTERVIEWER: _talking_interviewer(reply)})
    run = await queued_run(engine, stage="interviewing")

    await run_job(ctx, run)

    tokens = _of(await events_of(redis, run), RunEventType.TOKEN)
    text = "".join(e.data["text"] for e in tokens)
    assert (await run_row(engine, run)).status == "succeeded"
    assert text == " ".join(WORDS)
    assert {e.data["node"] for e in tokens} == {"interviewer"}
    assert 0 < len(tokens) < len(WORDS)  # batched, not one event per piece


async def test_tokens_are_published_before_the_event_that_follows_them(
    engine: AsyncEngine,
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
) -> None:
    ctx = job_ctx(
        redis,
        app_sessions,
        {Specialist.INTERVIEWER: _talking_interviewer(AIMessage(content="one two three"))},
    )
    run = await queued_run(engine, stage="interviewing")

    await run_job(ctx, run)

    kinds = [e.type for e in await events_of(redis, run)]
    first_finished = kinds.index(RunEventType.NODE_FINISHED)
    assert max(i for i, k in enumerate(kinds) if k is RunEventType.TOKEN) < first_finished


async def test_a_tool_call_is_published_by_name_without_its_arguments(
    engine: AsyncEngine,
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
) -> None:
    ctx = job_ctx(redis, app_sessions, {Specialist.INTERVIEWER: _tool_calling_interviewer()})
    run = await queued_run(engine, stage="interviewing")

    await run_job(ctx, run)

    events = await events_of(redis, run)
    calls = _of(events, RunEventType.TOOL_CALL)
    assert [e.data for e in calls] == [{"node": "interviewer", "name": "fake_tool"}]
    assert "private plan" not in repr(events)
