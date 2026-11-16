"""Provider-neutral interfaces that agent code depends on. Adapters implement them."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from pydantic import BaseModel

ToolDefinition = dict[str, object] | type[BaseModel] | Callable[..., object] | BaseTool


class LLMProvider(Protocol):
    """An async chat model that can bind tools. One instance serves one workspace's key."""

    def bind_tools(self, tools: Sequence[ToolDefinition]) -> LLMProvider:
        """A copy of this model that may call ``tools``."""
        ...

    async def ainvoke(
        self, messages: Sequence[BaseMessage], config: RunnableConfig | None = None
    ) -> AIMessage:
        """One chat call. Provider failures raise ``UpstreamError`` with a safe reason."""
        ...

    async def aclose(self) -> None:
        """Release the HTTP client."""
        ...
