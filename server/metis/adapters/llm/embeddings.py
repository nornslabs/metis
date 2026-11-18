"""OpenAI-compatible embeddings, called through the ``openai`` client's ``/embeddings``.

Like the chat model, it receives decrypted credentials as arguments and turns every
provider failure into an ``UpstreamError`` with a safe reason. A provider or model without
embeddings (404, or a 400 with code ``model_not_found``) is ``not_supported``, so callers
can fall back to search without vectors.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx
import openai

from metis.adapters.llm.chat import CALL_TIMEOUT_SECONDS, MAX_RETRIES, PROVIDER, map_error
from metis.core.ports import EmbeddingBatch
from metis.helpers.http import FailureReason, provider_error

MODEL_NOT_FOUND_CODE = "model_not_found"


class OpenAICompatibleEmbedder:
    """An ``Embedder`` over an OpenAI-compatible endpoint."""

    def __init__(self, client: openai.AsyncOpenAI, model: str, http_client: httpx.AsyncClient):
        self._client = client
        self._model = model
        self._http_client = http_client

    @property
    def model(self) -> str:
        return self._model

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        try:
            response = await self._client.embeddings.create(
                model=self._model, input=list(texts), encoding_format="float"
            )
            vectors = tuple(
                tuple(float(x) for x in item.embedding)
                for item in sorted(response.data, key=lambda item: item.index)
            )
            input_tokens = response.usage.prompt_tokens if response.usage else 0
        except Exception as exc:  # noqa: BLE001 - mapped to one safe error, nothing chained
            raise _map_error(exc) from None
        if len(vectors) != len(texts):
            raise provider_error(PROVIDER, FailureReason.BAD_RESPONSE)
        return EmbeddingBatch(vectors=vectors, input_tokens=input_tokens)

    async def aclose(self) -> None:
        await self._http_client.aclose()


def build_embedder(
    *, base_url: str, api_key: str, model: str, http_client: httpx.AsyncClient | None = None
) -> OpenAICompatibleEmbedder:
    """An embedder for one workspace's endpoint and key. ``http_client`` lets tests route
    to a fake server."""
    client = http_client or httpx.AsyncClient(follow_redirects=False)
    openai_client = openai.AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=CALL_TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
        # openai 3 is typed against ``httpx2`` but drives an ``httpx`` client as well (the chat
        # model hands it one through ``ChatOpenAI.http_async_client``); tests rely on that.
        http_client=client,  # type: ignore[arg-type]
    )
    return OpenAICompatibleEmbedder(openai_client, model, client)


def _map_error(exc: Exception) -> Exception:
    if isinstance(exc, openai.NotFoundError):
        return provider_error(PROVIDER, FailureReason.NOT_SUPPORTED)
    if isinstance(exc, openai.BadRequestError) and exc.code == MODEL_NOT_FOUND_CODE:
        return provider_error(PROVIDER, FailureReason.NOT_SUPPORTED)
    return map_error(exc)
