"""OpenAI-compatible chat model built on ``langchain-openai``.

Only this package imports ``langchain_openai`` / ``openai``. It receives decrypted
credentials as arguments (an adapter never imports a module) and turns every
provider failure into an ``UpstreamError`` carrying only a safe reason. Keys,
prompts and upstream bodies never reach an error or a log.
"""

from __future__ import annotations

import asyncio
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

from metis.core.errors import UpstreamError, UpstreamTimeoutError
from metis.core.ports import ToolDefinition
from metis.helpers.http import FailureReason, provider_error

PROVIDER = "llm"
CALL_TIMEOUT_SECONDS = 60.0
MAX_RETRIES = 2
RETRY_BASE_DELAY_SECONDS = 0.5
# A timeout is never retried: a call that timed out once usually times out again.
RETRYABLE_REASONS = frozenset(
    {
        FailureReason.RATE_LIMITED.value,
        FailureReason.SERVER_ERROR.value,
        FailureReason.UNREACHABLE.value,
    }
)
# These write a whole document in one answer, so they get the long timeout.
LONG_OUTPUT_PURPOSES = frozenset({"spec", "plan"})
DEFAULT_TEMPERATURE = 0.3
# Steadier for scoring and structured output, looser for conversation.
TEMPERATURE_BY_PURPOSE: dict[str, float] = {
    "interview": 0.7,
    "research": 0.3,
    "score": 0.0,
    "advise": 0.5,
    "gate": 0.0,
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
        reply = await self._invoke_with_retries(messages, config)
        if not isinstance(reply, AIMessage):
            raise provider_error(PROVIDER, FailureReason.BAD_RESPONSE)
        return reply

    async def aclose(self) -> None:
        await self._close()

    async def _invoke_with_retries(
        self, messages: Sequence[BaseMessage], config: RunnableConfig | None
    ) -> BaseMessage:
        """One call, retried only for failures that can recover (never for a timeout)."""
        attempt = 0
        while True:
            try:
                return await self._model.ainvoke(list(messages), config)
            except Exception as exc:  # noqa: BLE001 - mapped to one safe error, nothing chained
                mapped = map_error(exc)
                if attempt >= MAX_RETRIES or not _is_retryable(mapped):
                    raise mapped from None
            await asyncio.sleep(RETRY_BASE_DELAY_SECONDS * 2**attempt)
            attempt += 1


def build_chat_model(
    *,
    base_url: str,
    api_key: str,
    model: str,
    purpose: str,
    timeout_seconds: float,
    long_timeout_seconds: float,
    callbacks: Sequence[BaseCallbackHandler] = (),
    http_client: httpx.AsyncClient | None = None,
) -> OpenAICompatibleChat:
    """A chat model for one workspace's endpoint, key and model.

    ``purpose`` picks the temperature and the call timeout (``long_timeout_seconds`` for
    spec and plan, else ``timeout_seconds``). Retries are ours, not the SDK's, so a timeout
    is not retried. ``http_client`` lets tests route to a fake server.
    """
    client = http_client or httpx.AsyncClient(follow_redirects=False)
    chat = ChatOpenAI(
        base_url=base_url,
        api_key=SecretStr(api_key),
        model=model,
        temperature=TEMPERATURE_BY_PURPOSE.get(purpose, DEFAULT_TEMPERATURE),
        timeout=long_timeout_seconds if purpose in LONG_OUTPUT_PURPOSES else timeout_seconds,
        max_retries=0,
        http_async_client=client,
        callbacks=list(callbacks),
    )
    return OpenAICompatibleChat(chat, client.aclose)


def map_error(exc: Exception) -> Exception:
    """The safe ``UpstreamError`` for a failed provider call (unknown errors pass through)."""
    reason = _reason(exc)
    if reason is None:
        return exc
    error = provider_error(PROVIDER, reason)
    if reason is FailureReason.TIMEOUT:
        return UpstreamTimeoutError(error.detail, meta=error.meta)
    return error


def _is_retryable(error: Exception) -> bool:
    if not isinstance(error, UpstreamError):
        return False
    return (error.meta or {}).get("reason") in RETRYABLE_REASONS


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
