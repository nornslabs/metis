"""Workspace-scoped LLM gateway used by worker-side agent runs."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.adapters.llm import OpenAICompatibleClient
from metis.core.errors import ProviderNotConfiguredError
from metis.core.ports import LLMProvider
from metis.helpers.http import ClientFactory
from metis.modules.identity import ProviderKind, get_key_for_use


@asynccontextmanager
async def llm_provider(
    session: AsyncSession,
    workspace_id: UUID,
    make_client: ClientFactory,
) -> AsyncGenerator[LLMProvider]:
    """Yield the configured workspace provider and close its HTTP client afterward."""
    credentials = await get_key_for_use(session, workspace_id, ProviderKind.LLM)
    if credentials.base_url is None or credentials.model is None:
        raise ProviderNotConfiguredError("Save an LLM endpoint and model in workspace settings")

    provider = OpenAICompatibleClient(
        make_client,
        credentials.base_url,
        credentials.api_key,
        credentials.model,
    )
    try:
        yield provider
    finally:
        await provider.aclose()
