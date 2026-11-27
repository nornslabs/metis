"""Langfuse tracing for LLM calls: on only when ``LANGFUSE_*`` are all set."""

from __future__ import annotations

from collections.abc import Mapping

from langchain_core.callbacks import BaseCallbackHandler
from langfuse import Langfuse, get_client
from langfuse.langchain import CallbackHandler

from metis.core.config import Settings
from metis.core.logging import get_logger

logger = get_logger(__name__)


def tracing_callbacks(settings: Settings) -> list[BaseCallbackHandler]:
    """The Langfuse callback, or nothing when tracing is not configured."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return []
    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    return [CallbackHandler()]


def record_gate_span(settings: Settings, fields: Mapping[str, str]) -> None:
    """Record one gate decision as a Langfuse span; nothing when tracing is not configured.

    A tracing failure is logged and never reaches the gate.
    """
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return
    try:
        span = get_client().start_observation(
            name=f"gate:{fields['gate']}", as_type="span", metadata=dict(fields)
        )
        span.end()
    except Exception:  # noqa: BLE001  (tracing must never change what a gate decides)
        logger.warning("gate.span_failed")
