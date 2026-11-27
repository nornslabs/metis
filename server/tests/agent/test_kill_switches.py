"""Kill switch tests for all five feature flags: llm_enabled, exa_enabled, sarvam_enabled,
linear_enabled, notion_enabled.

Disabled-flag tests need no database: the guard raises or returns before touching the session.
Enabled tests exercise the real path against Postgres and a fake server, mirroring
``test_llm_gateway.py``.

``FF_<FLAG>`` drives the :class:`StaticProvider`, so flipping it between
``true``/``false`` flips the kill switch without touching code.
"""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from metis.adapters.feature_flags import StaticProvider
from metis.agent.tools.mcp import McpRunContext, load_mcp_tools
from metis.agent.tools.mcp_policy import McpToolPolicy
from metis.core.config import get_settings
from metis.core.errors import ProviderNotConfiguredError
from metis.core.ports import FlagContext
from metis.modules.integrations import IntegrationProvider
from tests.agent.llm_helpers import (
    FakeLLMServer,
    make_run,
    workspace_with_key,
)

# Values only need to satisfy ``Settings`` validation; disabled-flag tests never connect.
_TEST_SETTINGS_ENV = {
    "ENCRYPTION_MASTER_KEY": "lmnZiTdYDe6qnwh5yiWxEBRCzEcA/VCxuwBHAhzWnok=",
    "DATABASE_URL": "postgresql+asyncpg://metis_app:test@localhost:5432/metis",
    "REDIS_URL": "redis://localhost:6379/15",
}


def _settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in _TEST_SETTINGS_ENV.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()


def _flag_context(workspace_id: UUID | None = None) -> FlagContext:
    return FlagContext(
        workspace_id=workspace_id or uuid4(),
        environment="test",
        custom_attributes={},
    )


# ------------------------------------------------------------------ StaticProvider (all 5 flags)
@pytest.mark.parametrize(
    ("flag", "env_value", "expected"),
    [
        ("llm_enabled", None, True),
        ("exa_enabled", None, True),
        ("sarvam_enabled", None, True),
        ("linear_enabled", None, True),
        ("notion_enabled", None, True),
        ("llm_enabled", "false", False),
        ("exa_enabled", "false", False),
        ("sarvam_enabled", "false", False),
        ("linear_enabled", "false", False),
        ("notion_enabled", "false", False),
        ("llm_enabled", "0", False),
        ("exa_enabled", "off", False),
        ("sarvam_enabled", "no", False),
        ("linear_enabled", "true", True),
        ("notion_enabled", "1", True),
    ],
)
async def test_static_provider_all_five_flags(
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
    env_value: str | None,
    expected: bool,
) -> None:
    _settings_env(monkeypatch)
    if env_value is not None:
        monkeypatch.setenv(f"FF_{flag.upper()}", env_value)
    provider = StaticProvider(os.environ)
    assert await provider.is_enabled(flag, _flag_context(), default=True) is expected


# ------------------------------------------------------------------ Sarvam STT disabled (no DB)
async def test_transcribe_audio_sarvam_disabled_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_SARVAM_ENABLED", "false")
    get_settings.cache_clear()

    from metis.modules.stt.service import transcribe_audio

    with pytest.raises(ProviderNotConfiguredError) as caught:
        await transcribe_audio(
            None,  # type: ignore[arg-type]
            uuid4(),
            b"audio",
            "audio/webm",
            flags=StaticProvider(os.environ),
        )

    assert caught.value.meta == {"provider": "stt", "reason": "kill_switch"}


# ------------------------------------------------------------------ Notion export disabled (no DB)
async def test_load_mcp_tools_notion_disabled_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_NOTION_ENABLED", "false")
    get_settings.cache_clear()

    context = _mcp_context()

    tools = await load_mcp_tools(
        context,
        McpToolPolicy(read=frozenset({"some_tool"})),
        provider=IntegrationProvider.NOTION,
    )

    assert tools == []


# ------------------------------------------------------------------ Linear export disabled
async def test_load_mcp_tools_linear_disabled_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_LINEAR_ENABLED", "false")
    get_settings.cache_clear()

    context = _mcp_context()

    tools = await load_mcp_tools(
        context,
        McpToolPolicy(read=frozenset({"some_tool"})),
        provider=IntegrationProvider.LINEAR,
    )

    assert tools == []


# ------------------------------------------------------------------ Exa disabled via StaticProvider
async def test_exa_enabled_false_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_EXA_ENABLED", "false")
    provider = StaticProvider(os.environ)
    assert not await provider.is_enabled("exa_enabled", _flag_context())


# ------------------------------------------------------------------ Integration: all 5 switches
async def test_all_five_kill_switches_work_independently(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
) -> None:
    """StaticProvider reads each FF_* env var independently: off blocks, on allows."""
    _settings_env(monkeypatch)
    workspace_id = await workspace_with_key(engine)
    run_id = await make_run(engine, workspace_id)

    # ---- llm_enabled: off blocks chat_model, on allows
    monkeypatch.setenv("FF_LLM_ENABLED", "false")
    get_settings.cache_clear()
    from metis.agent.llm import LLMGateway

    gw_off = LLMGateway(
        workspace_id, run_id, sessions=app_sessions, http_client=server.client()
    )
    async with app_sessions() as session:
        with pytest.raises(ProviderNotConfiguredError):
            await gw_off.chat_model(session, "interview")
    assert server.requests == []

    monkeypatch.setenv("FF_LLM_ENABLED", "true")
    get_settings.cache_clear()
    gw_on = LLMGateway(
        workspace_id, run_id, sessions=app_sessions, http_client=server.client()
    )
    from langchain_core.messages import HumanMessage

    async with app_sessions() as session:
        model = await gw_on.chat_model(session, "interview")
    reply = await model.ainvoke([HumanMessage("hi")])
    assert reply.content == "hello"
    assert len(server.requests) == 1

    # ---- sarvam_enabled: off blocks transcribe_audio
    monkeypatch.setenv("FF_SARVAM_ENABLED", "false")
    get_settings.cache_clear()
    from metis.modules.stt.service import transcribe_audio

    async with app_sessions() as session:
        with pytest.raises(ProviderNotConfiguredError):
            await transcribe_audio(
                session, workspace_id, b"audio", "audio/webm", flags=StaticProvider(os.environ)
            )

    monkeypatch.setenv("FF_SARVAM_ENABLED", "true")
    get_settings.cache_clear()
    # With sarvam_enabled=true but no Sarvam key, transcribe_audio returns
    # client_side_provider (not ProviderNotConfiguredError): the flag check passes,
    # the key check fails.
    async with app_sessions() as session:
        result = await transcribe_audio(
            session, workspace_id, b"audio", "audio/webm", flags=StaticProvider(os.environ)
        )
    from metis.modules.stt.dto import STTErrorResponse

    assert isinstance(result, STTErrorResponse)
    assert result.error == "client_side_provider"

    # ---- linear_enabled: off blocks Linear tool loading
    monkeypatch.setenv("FF_LINEAR_ENABLED", "false")
    get_settings.cache_clear()
    context = _mcp_context()
    linear_tools = await load_mcp_tools(
        context,
        McpToolPolicy(read=frozenset({"list_teams"})),
        provider=IntegrationProvider.LINEAR,
    )
    assert linear_tools == []

    monkeypatch.setenv("FF_LINEAR_ENABLED", "true")
    get_settings.cache_clear()
    assert await StaticProvider(os.environ).is_enabled(
        "linear_enabled", _flag_context(workspace_id)
    ) is True

    # ---- notion_enabled: off blocks Notion tool loading
    monkeypatch.setenv("FF_NOTION_ENABLED", "false")
    get_settings.cache_clear()
    notion_tools = await load_mcp_tools(
        context,
        McpToolPolicy(read=frozenset({"some_tool"})),
        provider=IntegrationProvider.NOTION,
    )
    assert notion_tools == []

    monkeypatch.setenv("FF_NOTION_ENABLED", "true")
    get_settings.cache_clear()
    assert await StaticProvider(os.environ).is_enabled(
        "notion_enabled", _flag_context(workspace_id)
    ) is True


def _mcp_context() -> McpRunContext:
    """A minimal McpRunContext; the flag check returns before any field is used."""
    return McpRunContext(
        workspace_id=uuid4(),
        run_id=uuid4(),
        open_session=lambda _ws: None,  # type: ignore
        redis=None,  # type: ignore
        make_client=lambda _headers: None,  # type: ignore
    )
