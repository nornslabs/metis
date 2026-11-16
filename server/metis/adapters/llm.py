"""OpenAI-compatible adapter for model checks and agent chat calls."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import httpx
from langchain_core.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelTimeoutError,
)
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAIError
from pydantic import BaseModel, ValidationError

from metis.core.errors import ProviderNotConfiguredError
from metis.core.ports import LLMProvider, ToolDefinition
from metis.helpers.http import (
    PROVIDER_TIMEOUT_SECONDS,
    ClientFactory,
    FailureReason,
    capped,
    provider_error,
    send,
)

PROVIDER = "llm"


class _Model(BaseModel):
    id: str


class _ModelList(BaseModel):
    data: list[_Model]


class OpenAICompatibleClient:
    """An OpenAI-compatible endpoint for model checks and agent chat calls."""

    def __init__(
        self,
        make_client: ClientFactory,
        base_url: str,
        api_key: str,
        model: str | None = None,
    ) -> None:
        self._make_client = make_client
        self._base_url = base_url
        self._api_key = api_key
        self._model_name = model
        self._http: httpx.AsyncClient | None = None
        self._chat: ChatOpenAI | None = None

    def _chat_model(self) -> ChatOpenAI:
        if self._chat is None:
            if self._model_name is None:
                raise ProviderNotConfiguredError("Save an LLM model in workspace settings")
            self._http = self._make_client({})
            self._chat = ChatOpenAI(
                model=self._model_name,
                base_url=self._base_url,
                api_key=self._api_key,
                http_async_client=self._http,
                max_retries=0,
                timeout=PROVIDER_TIMEOUT_SECONDS,
            )
        return self._chat

    async def list_models(self) -> list[str]:
        """Return model ids from ``GET {base_url}/models``."""
        async with self._make_client({}) as http:
            request = http.build_request(
                "GET",
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            body = await send(http, PROVIDER, request)
        try:
            return [model.id for model in _ModelList.model_validate(body).data]
        except ValidationError:
            raise provider_error(PROVIDER, FailureReason.BAD_RESPONSE) from None

    def bind_tools(self, tools: Sequence[ToolDefinition], **kwargs: object) -> LLMProvider:
        """Bind OpenAI-compatible tools and return another provider view."""
        bound = cast(
            Runnable[Sequence[BaseMessage], AIMessage],
            self._chat_model().bind_tools(tools, **kwargs),
        )
        return _BoundOpenAICompatibleModel(self, bound)

    async def ainvoke(
        self,
        messages: Sequence[BaseMessage],
        config: RunnableConfig | None = None,
    ) -> AIMessage:
        """Make one bounded chat call; returned usage metadata stays with the message."""
        return await self._invoke(self._chat_model(), messages, config)

    async def aclose(self) -> None:
        """Close the HTTP client shared by chat calls for this run."""
        if self._http is not None:
            await self._http.aclose()

    async def _invoke(
        self,
        model: Runnable[Sequence[BaseMessage], AIMessage],
        messages: Sequence[BaseMessage],
        config: RunnableConfig | None,
    ) -> AIMessage:
        try:
            async with capped(PROVIDER):
                response = await model.ainvoke(messages, config=config)
        except APITimeoutError:
            raise provider_error(PROVIDER, FailureReason.TIMEOUT) from None
        except ModelTimeoutError:
            raise provider_error(PROVIDER, FailureReason.TIMEOUT) from None
        except APIConnectionError:
            raise provider_error(PROVIDER, FailureReason.UNREACHABLE) from None
        except ModelConnectionError:
            raise provider_error(PROVIDER, FailureReason.UNREACHABLE) from None
        except ModelAuthenticationError:
            raise provider_error(PROVIDER, FailureReason.UNAUTHORIZED) from None
        except APIStatusError as error:
            reason = (
                FailureReason.UNAUTHORIZED
                if error.status_code in {401, 403}
                else FailureReason.BAD_RESPONSE
            )
            raise provider_error(PROVIDER, reason) from None
        except OpenAIError:
            raise provider_error(PROVIDER, FailureReason.BAD_RESPONSE) from None
        except ModelAPIError:
            raise provider_error(PROVIDER, FailureReason.BAD_RESPONSE) from None
        except httpx.HTTPError:
            raise provider_error(PROVIDER, FailureReason.UNREACHABLE) from None
        if not isinstance(response, AIMessage):
            raise provider_error(PROVIDER, FailureReason.BAD_RESPONSE)
        return response


class _BoundOpenAICompatibleModel:
    """A tool-bound view that shares its parent client lifecycle."""

    def __init__(
        self,
        client: OpenAICompatibleClient,
        model: Runnable[Sequence[BaseMessage], AIMessage],
    ) -> None:
        self._client = client
        self._model = model

    def bind_tools(self, tools: Sequence[ToolDefinition], **kwargs: object) -> LLMProvider:
        bound = cast(
            Runnable[Sequence[BaseMessage], AIMessage],
            self._model.bind_tools(tools, **kwargs),
        )
        return _BoundOpenAICompatibleModel(self._client, bound)

    async def ainvoke(
        self,
        messages: Sequence[BaseMessage],
        config: RunnableConfig | None = None,
    ) -> AIMessage:
        return await self._client._invoke(self._model, messages, config)

    async def aclose(self) -> None:
        await self._client.aclose()
