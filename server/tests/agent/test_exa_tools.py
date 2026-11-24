"""Exa agent tools exercise the hosted MCP protocol without network calls."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx
import pytest

from metis.agent.tools import exa as exa_tools
from metis.core.errors import UpstreamError
from metis.core.events import RunEventType
from tests.modules.identity.fake_exa_mcp import ExaMode, FakeExaMcp

RUN_ID = UUID("00000000-0000-0000-0000-000000000226")
WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000217")


class MemoryRedis:
    """Only the Redis cache and stream operations these tool tests use."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.entries: list[tuple[bytes, dict[bytes, bytes]]] = []

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        assert ex == 3_600
        self.values[key] = value

    def pipeline(self, *, transaction: bool) -> MemoryPipeline:
        assert transaction
        return MemoryPipeline(self)

    async def xrange(self, key: str) -> list[tuple[bytes, dict[bytes, bytes]]]:
        assert key == f"run:{RUN_ID}"
        return self.entries


class MemoryPipeline:
    def __init__(self, redis: MemoryRedis) -> None:
        self.redis = redis
        self.pending: list[dict[bytes, bytes]] = []

    async def __aenter__(self) -> MemoryPipeline:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def xadd(self, _key: str, fields: dict[str, str], **_kwargs: Any) -> None:
        self.pending.append({k.encode(): v.encode() for k, v in fields.items()})

    async def execute(self) -> list[bytes]:
        ids = []
        for fields in self.pending:
            event_id = f"{len(self.redis.entries) + 1}-0".encode()
            self.redis.entries.append((event_id, fields))
            ids.append(event_id)
        return ids


@pytest.fixture
def redis() -> MemoryRedis:
    return MemoryRedis()


@pytest.mark.asyncio
async def test_loads_scoped_tools_normalizes_caps_caches_and_emits_events(
    redis: MemoryRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with FakeExaMcp().running() as fake:

        async def get_key(*_args: object) -> SimpleNamespace:
            return SimpleNamespace(api_key="workspace-exa-key")

        monkeypatch.setattr(exa_tools, "get_key_for_use", get_key)
        factory = lambda headers: httpx.AsyncClient(  # noqa: E731
            transport=fake.transport(), headers=dict(headers)
        )

        async with exa_tools.load_exa_tools(
            None,
            WORKSPACE_ID,
            RUN_ID,
            redis,
            factory,  # type: ignore[arg-type]
        ) as tools:
            assert set(tools) == exa_tools.RESEARCHER_TOOLS
            researcher_tools = exa_tools.exa_tools_for("researcher", tools)
            assert {tool.name for tool in researcher_tools} == set(tools)
            assert {tool.name for tool in exa_tools.exa_tools_for("scorer", tools)} == {
                exa_tools.SEARCH_TOOL
            }
            assert {tool.name for tool in exa_tools.exa_tools_for("advisor", tools)} == {
                exa_tools.SEARCH_TOOL
            }

            args = {"query": "market", "objective": "find sources", "numResults": 99}
            hits = await tools[exa_tools.SEARCH_TOOL].ainvoke(args)
            repeated = await tools[exa_tools.SEARCH_TOOL].ainvoke(args)
            assert hits == repeated
            assert hits == [
                {
                    "url": "https://example.com",
                    "title": "Example",
                    "published_at": None,
                    "snippet": "",
                    "source": "exa",
                }
            ]
            assert fake.tool_calls[0]["numResults"] == 10
            assert len(fake.tool_calls) == 1

            fetched = await tools[exa_tools.FETCH_TOOL].ainvoke({"url": "https://example.com"})
            assert len(fetched["content"]) == 4_000

    stream = await redis.xrange(f"run:{RUN_ID}")
    assert len(stream) == 3
    assert all(entry[b"type"].decode() == RunEventType.TOOL_CALL.value for _, entry in stream)
    assert set(fake.api_keys) == {"workspace-exa-key"}


@pytest.mark.asyncio
async def test_mcp_tool_auth_error_maps_to_safe_provider_error(
    redis: MemoryRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with FakeExaMcp().running() as fake:
        fake.mode = ExaMode.BAD_KEY

        async def get_key(*_args: object) -> SimpleNamespace:
            return SimpleNamespace(api_key="workspace-exa-key")

        monkeypatch.setattr(exa_tools, "get_key_for_use", get_key)
        factory = lambda headers: httpx.AsyncClient(  # noqa: E731
            transport=fake.transport(), headers=dict(headers)
        )
        async with exa_tools.load_exa_tools(
            None,
            WORKSPACE_ID,
            RUN_ID,
            redis,
            factory,  # type: ignore[arg-type]
        ) as tools:
            with pytest.raises(UpstreamError) as exc_info:
                await tools[exa_tools.SEARCH_TOOL].ainvoke(
                    {"query": "market", "objective": "find sources"}
                )
        assert exc_info.value.meta == {"provider": "exa", "reason": "unauthorized"}


@pytest.mark.asyncio
async def test_mcp_server_error_retries_twice_and_maps_reason(
    redis: MemoryRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with FakeExaMcp().running() as fake:
        fake.mode = ExaMode.TOOL_ERROR

        async def get_key(*_args: object) -> SimpleNamespace:
            return SimpleNamespace(api_key="workspace-exa-key")

        monkeypatch.setattr(exa_tools, "get_key_for_use", get_key)
        factory = lambda headers: httpx.AsyncClient(  # noqa: E731
            transport=fake.transport(), headers=dict(headers)
        )
        async with exa_tools.load_exa_tools(
            None,
            WORKSPACE_ID,
            RUN_ID,
            redis,
            factory,  # type: ignore[arg-type]
        ) as tools:
            with pytest.raises(UpstreamError) as exc_info:
                await tools[exa_tools.SEARCH_TOOL].ainvoke(
                    {"query": "market", "objective": "find sources"}
                )
        assert exc_info.value.meta == {"provider": "exa", "reason": "server_error"}
        assert len(fake.tool_calls) == 3
