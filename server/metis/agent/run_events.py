"""Turns the graph's stream into run events on the Redis stream.

``astream(stream_mode=["updates", "messages", "custom", "tasks"])`` yields ``(mode, chunk)``
pairs; :meth:`RunEventPublisher.handle` maps each to ``core.events`` events:

- ``tasks`` start of a specialist → ``node_started {node}`` (the supervisor only routes, so
  it publishes nothing);
- ``custom`` ``node_finished`` / ``tool_call`` from a node → passed through;
- ``messages`` model output → ``token {node, text}`` (buffered, see below) and
  ``tool_call {node, name}`` (the arguments are never published);
- ``updates`` ``__interrupt__`` → returned to the caller, which stores it and publishes
  ``interrupt``.

Streamed text is buffered and sent as one ``token`` event about every 100 ms (a background
flusher), and always before any other event so the order stays true.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk
from redis.asyncio import Redis

from metis.adapters.mcp.exa import FETCH_TOOL, SEARCH_TOOL
from metis.agent.supervisor import SUPERVISOR_NODE
from metis.core import events
from metis.core.events import RunEventType
from metis.core.logging import get_logger

TOKEN_FLUSH_SECONDS = 0.1
INTERRUPT_KEY = "__interrupt__"
# Event types a node may emit itself through the stream writer.
NODE_EVENT_TYPES = frozenset({RunEventType.NODE_FINISHED, RunEventType.TOOL_CALL})

logger = get_logger(__name__)
EXECUTION_REPORTED_TOOLS = frozenset({SEARCH_TOOL, FETCH_TOOL})


class RunEventPublisher:
    """Publishes one run's events; the caller owns the Redis client."""

    def __init__(self, run_id: str, redis: Redis) -> None:
        self._run_id = run_id
        self._redis = redis
        self._tokens: list[tuple[str, str]] = []
        self._lock = asyncio.Lock()

    async def publish(self, type: RunEventType, data: Mapping[str, Any]) -> None:  # noqa: A002
        """Publish an event after any buffered text, so order is kept."""
        async with self._lock:
            await self._flush_locked()
            await events.publish(self._run_id, type, data, redis=self._redis)

    async def status(self, status: str, **extra: Any) -> None:
        """Publish ``run_status``; a terminal status also starts the stream's TTL."""
        await self.publish(RunEventType.RUN_STATUS, {"status": status, **extra})

    async def handle(self, mode: str, chunk: Any) -> dict[str, Any] | None:
        """Publish what ``chunk`` means; return the interrupt payload if it carries one."""
        if mode == "tasks":
            await self._task(chunk)
        elif mode == "custom":
            await self._custom(chunk)
        elif mode == "messages":
            await self._message(chunk)
        elif mode == "updates":
            return _interrupt_payload(chunk)
        return None

    async def flush(self) -> None:
        """Publish any buffered text now."""
        async with self._lock:
            await self._flush_locked()

    @asynccontextmanager
    async def flushing(self) -> AsyncGenerator[None]:
        """Flush buffered text every ``TOKEN_FLUSH_SECONDS`` while the block runs and at its end."""
        task = asyncio.create_task(self._flush_forever())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await self.flush()

    async def _flush_forever(self) -> None:
        while True:
            await asyncio.sleep(TOKEN_FLUSH_SECONDS)
            await self.flush()

    async def _flush_locked(self) -> None:
        batch, self._tokens = self._tokens, []
        for node, text in _merge_by_node(batch):
            await events.publish(
                self._run_id, RunEventType.TOKEN, {"node": node, "text": text}, redis=self._redis
            )

    async def _task(self, chunk: Mapping[str, Any]) -> None:
        # A task start carries ``input``; its end carries ``result`` instead.
        name = chunk.get("name")
        if "input" in chunk and name and name != SUPERVISOR_NODE:
            await self.publish(RunEventType.NODE_STARTED, {"node": name})

    async def _custom(self, chunk: Any) -> None:
        if not isinstance(chunk, Mapping):
            return
        try:
            event_type = RunEventType(str(chunk.get("type")))
        except ValueError:
            logger.warning("run.custom_event_ignored", type=str(chunk.get("type")))
            return
        if event_type in NODE_EVENT_TYPES:
            await self.publish(event_type, {k: v for k, v in chunk.items() if k != "type"})

    async def _message(self, chunk: Any) -> None:
        message, metadata = chunk
        if not isinstance(message, AIMessage | AIMessageChunk):
            return
        node = str(metadata.get("langgraph_node", ""))
        for name in _tool_names(message):
            # Exa reports after execution with query and result count; publishing here
            # as well would create a second event for the same call.
            if name not in EXECUTION_REPORTED_TOOLS:
                await self.publish(RunEventType.TOOL_CALL, {"node": node, "name": name})
        text = message.content if isinstance(message.content, str) else ""
        if text:
            async with self._lock:
                self._tokens.append((node, text))


def _tool_names(message: AIMessage | AIMessageChunk) -> list[str]:
    if isinstance(message, AIMessageChunk) and message.tool_call_chunks:
        return [name for c in message.tool_call_chunks if (name := c.get("name"))]
    return [call["name"] for call in message.tool_calls]


def _merge_by_node(batch: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Join consecutive pieces of text from the same node, keeping order."""
    merged: list[tuple[str, str]] = []
    for node, text in batch:
        if merged and merged[-1][0] == node:
            merged[-1] = (node, merged[-1][1] + text)
        else:
            merged.append((node, text))
    return merged


def _interrupt_payload(update: Mapping[str, Any]) -> dict[str, Any] | None:
    pending = update.get(INTERRUPT_KEY)
    if not pending:
        return None
    value = pending[0].value
    return dict(value) if isinstance(value, Mapping) else {"value": value}
