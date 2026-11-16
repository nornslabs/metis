"""Provider-neutral interfaces used by agent code."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from pydantic import BaseModel

ToolDefinition = dict[str, object] | type[BaseModel] | Callable[..., object] | BaseTool


class LLMProvider(Protocol):
    """An async chat model that can bind tools for an agent call."""

    def bind_tools(
        self, tools: Sequence[ToolDefinition], **kwargs: object
    ) -> LLMProvider: ...

    async def ainvoke(
        self,
        messages: Sequence[BaseMessage],
        config: RunnableConfig | None = None,
    ) -> AIMessage: ...

    async def aclose(self) -> None: ...
