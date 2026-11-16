"""The LLM gateway: the one way agent code gets a chat model.

``LLMGateway`` serves one run. It reads the workspace's saved credentials through
``identity.get_key_for_use`` only to build the model (it never stores or logs them),
caches one model per ``purpose`` for the run, and records the tokens and cost of every
completed call in ``ideas.llm_usage`` through ``ideas.record_llm_usage``.

Usage rows are written in their own short transaction, so a run that later fails
keeps what it already spent. Failing to record usage is logged and never fails the
call whose reply the run already paid for. Budget enforcement is SHIP-237.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

import httpx
from langchain_core.callbacks import AsyncCallbackHandler, BaseCallbackHandler
from langchain_core.outputs import ChatGeneration, LLMResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis.adapters.llm import OpenAICompatibleChat, build_chat_model
from metis.agent.tracing import tracing_callbacks
from metis.core.config import get_settings
from metis.core.db import get_session_maker, set_workspace, transaction
from metis.core.errors import ProviderNotConfiguredError
from metis.core.logging import get_logger
from metis.core.ports import LLMProvider
from metis.helpers.pricing import ModelPrice, cost_usd
from metis.modules.ideas import NewLlmUsage, record_llm_usage
from metis.modules.identity import ProviderKind, get_key_for_use

logger = get_logger(__name__)


class LLMGateway:
    """Chat models for one run of one workspace."""

    def __init__(
        self,
        workspace_id: UUID,
        run_id: UUID,
        *,
        sessions: async_sessionmaker[AsyncSession] | None = None,
        prices: Mapping[str, ModelPrice] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self._workspace_id = workspace_id
        self._run_id = run_id
        self._sessions = sessions or get_session_maker()
        self._prices = settings.llm_prices if prices is None else prices
        self._http_client = http_client
        self._tracing = tracing_callbacks(settings)
        self._models: dict[str, OpenAICompatibleChat] = {}

    async def chat_model(self, session: AsyncSession, purpose: str) -> LLMProvider:
        """The run's chat model for ``purpose``.

        ``session`` reads the saved key. Raises ``ProviderNotConfiguredError`` when the
        workspace has no LLM key.
        """
        cached = self._models.get(purpose)
        if cached is not None:
            return cached
        credentials = await get_key_for_use(session, self._workspace_id, ProviderKind.LLM)
        if credentials.base_url is None or credentials.model is None:
            raise ProviderNotConfiguredError("No LLM key is saved for this workspace.")
        model = build_chat_model(
            base_url=credentials.base_url,
            api_key=credentials.api_key,
            model=credentials.model,
            purpose=purpose,
            callbacks=[*self._tracing, self._usage_recorder(credentials.model)],
            http_client=self._http_client,
        )
        self._models[purpose] = model
        return model

    async def aclose(self) -> None:
        """Release every model's HTTP client; call when the run ends."""
        models, self._models = list(self._models.values()), {}
        for model in models:
            await model.aclose()

    def _usage_recorder(self, model: str) -> BaseCallbackHandler:
        return _UsageRecorder(self, model)

    async def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        usage = NewLlmUsage(
            run_id=self._run_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd(self._prices.get(model), input_tokens, output_tokens),
        )
        try:
            async with self._sessions() as session, transaction(session):
                await set_workspace(session, self._workspace_id)
                await record_llm_usage(session, self._workspace_id, usage)
        except Exception:
            logger.exception("llm.usage_record_failed", run_id=str(self._run_id), model=model)


class _UsageRecorder(AsyncCallbackHandler):
    """Writes a usage row when a call completes."""

    def __init__(self, gateway: LLMGateway, model: str) -> None:
        self._gateway = gateway
        self._model = model

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        input_tokens, output_tokens = _token_counts(response)
        await self._gateway.record(self._model, input_tokens, output_tokens)


def _token_counts(response: LLMResult) -> tuple[int, int]:
    """Tokens the provider reported, or ``(0, 0)`` when it reported none."""
    for generations in response.generations:
        for generation in generations:
            if isinstance(generation, ChatGeneration):
                usage = getattr(generation.message, "usage_metadata", None)
                if usage:
                    return int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
    return 0, 0
