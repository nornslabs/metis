"""OpenAI-compatible chat model built on ``langchain-openai``.

Only this package imports ``langchain_openai`` / ``openai``. It receives decrypted
credentials as arguments (an adapter never imports a module) and turns every
provider failure into an ``UpstreamError`` carrying only a safe reason. Keys,
prompts and upstream bodies never reach an error or a log.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Self

import httpx
import openai
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import SecretStr, ValidationError

from metis.core.ports import ToolDefinition
from metis.helpers.http import FailureReason, provider_error

PROVIDER = "llm"
CALL_TIMEOUT_SECONDS = 60.0
MAX_RETRIES = 2
DEFAULT_TEMPERATURE = 0.3
# Steadier for scoring and structured output, looser for conversation.
TEMPERATURE_BY_PURPOSE: dict[str, float] = {
    "interview": 0.7,
    "research": 0.3,
    "score": 0.0,
    "advise": 0.5,
    "spec": 0.2,
    "plan": 0.2,
}
SERVER_ERROR_FROM_STATUS = 500

type _Bound = Runnable[LanguageModelInput, BaseMessage]
type CloseHook = Callable[[], Awaitable[None]]


class OpenAICompatibleChat:
    """An ``LLMProvider`` over an OpenAI-compatible endpoint."""

    def __init__(self, model: _Bound, close: CloseHook) -> None:
        self._model = model
        self._close = close

    def bind_tools(self, tools: Sequence[ToolDefinition]) -> Self:
        if not isinstance(self._model, ChatOpenAI):
            raise TypeError("tools are already bound")
        return type(self)(self._model.bind_tools(list(tools)), self._close)

    async def ainvoke(
        self, messages: Sequence[BaseMessage], config: RunnableConfig | None = None
    ) -> AIMessage:
        try:
            reply = await self._model.ainvoke(list(messages), config)
        except Exception as exc:  # noqa: BLE001 - mapped to one safe error, nothing chained
            raise map_error(exc) from None
        if not isinstance(reply, AIMessage):
            raise provider_error(PROVIDER, FailureReason.BAD_RESPONSE)
        return reply

    async def aclose(self) -> None:
        await self._close()


def build_chat_model(
    *,
    base_url: str,
    api_key: str,
    model: str,
    purpose: str,
    callbacks: Sequence[BaseCallbackHandler] = (),
    http_client: httpx.AsyncClient | None = None,
) -> OpenAICompatibleChat:
    """A chat model for one workspace's endpoint, key and model.

    ``purpose`` picks the temperature. ``http_client`` lets tests route to a fake server.
    """
    client = http_client or httpx.AsyncClient(follow_redirects=False)
    chat = ChatOpenAI(
        base_url=base_url,
        api_key=SecretStr(api_key),
        model=model,
        temperature=TEMPERATURE_BY_PURPOSE.get(purpose, DEFAULT_TEMPERATURE),
        timeout=CALL_TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
        http_async_client=client,
        callbacks=list(callbacks),
    )
    return OpenAICompatibleChat(chat, client.aclose)


def map_error(exc: Exception) -> Exception:
    """The safe ``UpstreamError`` for a failed provider call (unknown errors pass through)."""
    reason = _reason(exc)
    if reason is None:
        return exc
    return provider_error(PROVIDER, reason)


def _reason(exc: Exception) -> FailureReason | None:
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return FailureReason.UNAUTHORIZED
    if isinstance(exc, openai.RateLimitError):
        return FailureReason.RATE_LIMITED
    if isinstance(exc, openai.APITimeoutError | httpx.TimeoutException):
        return FailureReason.TIMEOUT
    if isinstance(exc, openai.APIConnectionError | httpx.TransportError):
        return FailureReason.UNREACHABLE
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code >= SERVER_ERROR_FROM_STATUS:
            return FailureReason.SERVER_ERROR
        return FailureReason.BAD_RESPONSE
    if isinstance(exc, openai.OpenAIError | ValidationError | ValueError | KeyError | TypeError):
        return FailureReason.BAD_RESPONSE
    return None
