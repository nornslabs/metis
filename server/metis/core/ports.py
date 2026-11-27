"""Provider-neutral interfaces that agent code depends on. Adapters implement them."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

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


@dataclass(frozen=True)
class FlagContext:
    """Who a flag is read for, so a provider can target by workspace, user or attribute."""

    environment: str
    workspace_id: UUID | None = None
    user_id: UUID | None = None
    custom_attributes: Mapping[str, str | int | float | bool] = field(default_factory=dict)


class FeatureFlagProvider(Protocol):
    """Async feature flags and remote config. Reads never raise: a flag that is missing,
    malformed or unreachable gives the caller's ``default``."""

    async def is_enabled(self, key: str, context: FlagContext, default: bool = False) -> bool:
        """Whether the boolean flag ``key`` is on; ``default`` when it has no usable value."""
        ...

    async def get_string(self, key: str, context: FlagContext, default: str) -> str:
        """The string value of ``key``; ``default`` when it has none."""
        ...

    async def get_json(self, key: str, context: FlagContext, default: Any) -> Any:
        """The JSON value of ``key`` (any JSON type); ``default`` when absent or invalid."""
        ...

    async def close(self) -> None:
        """Release any client or background task. Safe to call twice."""
        ...
