"""LLM adapters: the model-list key check, the OpenAI-compatible chat model and embedder."""

from metis.adapters.llm.chat import OpenAICompatibleChat, build_chat_model
from metis.adapters.llm.client import OpenAICompatibleClient
from metis.adapters.llm.embeddings import OpenAICompatibleEmbedder, build_embedder

__all__ = [
    "OpenAICompatibleChat",
    "OpenAICompatibleClient",
    "OpenAICompatibleEmbedder",
    "build_chat_model",
    "build_embedder",
]
