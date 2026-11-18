"""Provider-neutral interfaces that agent code depends on. Adapters implement them."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True)
class EmbeddingBatch:
    """Vectors in the order of the texts, and the input tokens the provider reported."""

    vectors: tuple[tuple[float, ...], ...]
    input_tokens: int


class Embedder(Protocol):
    """An async text embedder. One instance serves one workspace's key and one model."""

    @property
    def model(self) -> str:
        """The embedding model id."""
        ...

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        """One embeddings call. Failures raise ``UpstreamError`` with a safe reason;
        ``not_supported`` when the provider has no embeddings for the model."""
        ...

    async def aclose(self) -> None:
        """Release the HTTP client."""
        ...
