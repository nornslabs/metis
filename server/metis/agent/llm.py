"""The LLM gateway: the one way agent code gets a chat model or embeddings.

``LLMGateway`` serves one run. It reads the workspace's saved credentials through
``identity.get_key_for_use`` only to build the model (it never stores or logs them),
caches one model per ``purpose`` for the run, and records the tokens and cost of every
completed call in ``ideas.llm_usage`` through ``ideas.record_llm_usage``.

``embed`` turns texts into 1536-dimension vectors with ``LLM_EMBEDDING_MODEL`` on the same
endpoint and key. A provider without embeddings (or with vectors of another size) gives
``None``, and the gateway stops asking for the rest of the run, so callers fall back to
search by name.

Usage rows are written in their own short transaction, so a run that later fails
keeps what it already spent. Failing to record usage is logged and never fails the
call whose reply the run already paid for. Budget enforcement is SHIP-237.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

import httpx
from langchain_core.callbacks import AsyncCallbackHandler, BaseCallbackHandler
from langchain_core.outputs import ChatGeneration, LLMResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis.adapters.feature_flags import build_feature_flag_provider
from metis.adapters.llm import OpenAICompatibleChat, build_chat_model, build_embedder
from metis.agent.tracing import tracing_callbacks
from metis.core.config import get_settings
from metis.core.db import get_session_maker, set_workspace, transaction
from metis.core.errors import (
    ProviderNotConfiguredError,
    UpstreamError,
    provider_not_configured,
)
from metis.core.logging import get_logger
from metis.core.ports import Embedder, FeatureFlagProvider, FlagContext, LLMProvider
from metis.helpers.http import FailureReason
from metis.helpers.pricing import ModelPrice, cost_usd
from metis.modules.ideas import NewLlmUsage, record_llm_usage
from metis.modules.identity import ProviderCredentials, ProviderKind, get_key_for_use
from metis.modules.research import EMBEDDING_DIMENSIONS

logger = get_logger(__name__)

_DEFAULT_RATE_LIMITS: dict[str, object] = {
    "default": {"requests_per_minute": 0},
}


def _flag_value(routing: dict[str, object], key: str) -> str | None:
    value = routing.get(key)
    return str(value) if value is not None else None


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
        flags: FeatureFlagProvider | None = None,
    ) -> None:
        settings = get_settings()
        self._workspace_id = workspace_id
        self._run_id = run_id
        self._sessions = sessions or get_session_maker()
        self._prices = settings.llm_prices if prices is None else prices
        self._http_client = http_client
        self._tracing = tracing_callbacks(settings)
        self._flags = flags or build_feature_flag_provider(settings)
        self._models: dict[str, OpenAICompatibleChat] = {}
        self._embedding_model = settings.llm_embedding_model
        self._call_timeout = settings.llm_call_timeout_seconds
        self._long_call_timeout = settings.llm_long_call_timeout_seconds
        self._embedder: Embedder | None = None
        self._embeddings_unavailable = False
        self._request_counts: dict[str, int] = {}

    async def _require_llm_enabled(self) -> None:
        """Raise ``ProviderNotConfiguredError`` when the ``llm_enabled`` kill switch is off.

        The ``FlagContext`` carries the run's workspace, the deployment environment and any
        custom attributes (a workspace tier, once one is stored on the workspace). The flag
        itself is decided by the configured provider, so this gateway never reads flags
        directly.
        """
        settings = get_settings()
        context = FlagContext(
            environment=settings.app_env,
            workspace_id=self._workspace_id,
        )
        if not await self._flags.is_enabled("llm_enabled", context, default=True):
            raise ProviderNotConfiguredError(
                "LLM calls are disabled: the ``llm_enabled`` kill switch is off.",
                meta={"provider": "llm", "reason": "kill_switch"},
            )

    async def chat_model(
        self, session: AsyncSession, purpose: str, tier: str = "default"
    ) -> LLMProvider:
        """The run's chat model for ``purpose``.

        ``session`` reads the saved key. Raises ``ProviderNotConfiguredError`` when the
        workspace has no LLM key, or when the ``llm_enabled`` kill switch is off.
        Model selection and per-tier rate limits come from the ``model_routing`` and
        ``rate_limits`` JSON flags.
        """
        await self._require_llm_enabled()

        context = FlagContext(
            workspace_id=self._workspace_id,
            environment=get_settings().app_env,
            custom_attributes={"tier": tier},
        )
        rate_limits = await self._flags.get_json("rate_limits", context, _DEFAULT_RATE_LIMITS)
        if not isinstance(rate_limits, dict):
            rate_limits = _DEFAULT_RATE_LIMITS
        tier_limits = rate_limits.get(tier, rate_limits.get("default", {}))
        if not isinstance(tier_limits, dict):
            tier_limits = {}
        limit = tier_limits.get("requests_per_minute", 0)
        if not isinstance(limit, int):
            limit = 0
        if limit > 0:
            count = self._request_counts.get(tier, 0) + 1
            self._request_counts[tier] = count
            if count > limit:
                raise ProviderNotConfiguredError(
                    f"Rate limit exceeded for tier {tier}: {limit} requests per minute.",
                    meta={"provider": "llm", "reason": "rate_limited", "tier": tier},
                )

        cached = self._models.get(purpose)
        if cached is not None:
            return cached
        credentials, base_url, _ = await self._credentials(session)
        assert credentials.model is not None

        # Default routing uses the workspace's saved model as the fallback.
        default_routing: dict[str, object] = {
            "default": credentials.model,
            "fallback": credentials.model,
        }
        routing = await self._flags.get_json("model_routing", context, default_routing)
        if not isinstance(routing, dict):
            routing = default_routing

        model_name: str | None = credentials.model
        for key in (tier, "default", "fallback"):
            value = _flag_value(routing, key)
            if value is not None:
                model_name = value
                break
        assert model_name is not None

        model = build_chat_model(
            base_url=base_url,
            api_key=credentials.api_key,
            model=model_name,
            purpose=purpose,
            timeout_seconds=self._call_timeout,
            long_timeout_seconds=self._long_call_timeout,
            callbacks=[*self._tracing, self._usage_recorder(model_name)],
            http_client=self._http_client,
        )
        self._models[purpose] = model
        return model

    async def embed(self, session: AsyncSession, texts: Sequence[str]) -> list[list[float]] | None:
        """One vector per text, or ``None`` when the provider has no usable embeddings.

        ``session`` reads the saved key. Records usage like a chat call. Raises
        ``ProviderNotConfiguredError`` without an LLM key and ``UpstreamError`` for other
        provider failures.
        """
        if not texts:
            return []
        await self._require_llm_enabled()
        if self._embeddings_unavailable:
            return None
        embedder = await self._get_embedder(session)
        try:
            batch = await embedder.embed(texts)
        except UpstreamError as exc:
            if (exc.meta or {}).get("reason") != FailureReason.NOT_SUPPORTED.value:
                raise
            self._no_embeddings("not_supported")
            return None
        await self.record(embedder.model, batch.input_tokens, 0)
        if any(len(vector) != EMBEDDING_DIMENSIONS for vector in batch.vectors):
            self._no_embeddings("wrong_dimensions")
            return None
        return [list(vector) for vector in batch.vectors]

    async def aclose(self) -> None:
        """Release every model's HTTP client; call when the run ends."""
        models, self._models = list(self._models.values()), {}
        for model in models:
            await model.aclose()
        embedder, self._embedder = self._embedder, None
        if embedder is not None:
            await embedder.aclose()

    async def _credentials(self, session: AsyncSession) -> tuple[ProviderCredentials, str, str]:
        """The workspace's LLM credentials with their ``base_url`` and chat ``model``."""
        credentials = await get_key_for_use(session, self._workspace_id, ProviderKind.LLM)
        if credentials.base_url is None or credentials.model is None:
            raise provider_not_configured(ProviderKind.LLM)
        return credentials, credentials.base_url, credentials.model

    async def _get_embedder(self, session: AsyncSession) -> Embedder:
        if self._embedder is None:
            credentials, base_url, _ = await self._credentials(session)
            self._embedder = build_embedder(
                base_url=base_url,
                api_key=credentials.api_key,
                model=self._embedding_model,
                http_client=self._http_client,
            )
        return self._embedder

    def _no_embeddings(self, reason: str) -> None:
        self._embeddings_unavailable = True
        logger.info(
            "llm.embeddings_unavailable",
            run_id=str(self._run_id),
            model=self._embedding_model,
            reason=reason,
        )

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
