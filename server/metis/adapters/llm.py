"""OpenAI-compatible LLM adapter.

Talks to any endpoint that speaks the OpenAI REST API (``base_url`` + bearer
key). Today it only lists models, which proves the URL and key work without
spending tokens; the LLM gateway (SHIP-220) adds chat calls here.
"""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from metis.helpers.http import ClientFactory, FailureReason, provider_error, send

PROVIDER = "llm"


class _Model(BaseModel):
    id: str


class _ModelList(BaseModel):
    data: list[_Model]


class OpenAICompatibleClient:
    """An OpenAI-compatible API at ``base_url`` (no trailing slash), used with ``api_key``."""

    def __init__(self, make_client: ClientFactory, base_url: str, api_key: str) -> None:
        self._make_client = make_client
        self._base_url = base_url
        self._api_key = api_key

    async def list_models(self) -> list[str]:
        """Ids of the models the key can use (``GET {base_url}/models``)."""
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
