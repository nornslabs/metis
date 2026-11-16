"""Langfuse tracing for LLM calls: on only when ``LANGFUSE_*`` are all set."""

from __future__ import annotations

from langchain_core.callbacks import BaseCallbackHandler
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from metis.core.config import Settings


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
