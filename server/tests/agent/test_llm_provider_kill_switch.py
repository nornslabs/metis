"""Per-provider LLM kill switch tests.

Tests that ``LLMGateway`` checks provider-specific flags
(``llm_openai_enabled``, ``llm_anthropic_enabled``, ``llm_google_enabled``,
``llm_local_enabled``) after the master ``llm_enabled`` switch, using the
provider determined from the workspace's saved credential base URL.

``FF_LLM_ENABLED`` and ``FF_LLM_<VENDOR>_ENABLED`` drive the
:class:`StaticProvider`, so flipping them between ``true``/``false`` flips
the kill switches without touching code.
"""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.adapters.feature_flags import StaticProvider
from metis.agent.llm import LLMGateway, _vendor_from_base_url
from metis.core.config import get_settings
from metis.core.errors import ProviderNotConfiguredError
from metis.core.ports import FlagContext
from metis.modules import auth, identity
from metis.modules.identity import MemberRole, Membership, ProviderKind
from metis.modules.identity.service.provider_keys import set_key
from tests.agent.llm_helpers import (
    LLM_KEY,
    LLM_MODEL,
    FakeLLMServer,
    make_run,
)
from tests.helpers.auth import create_user

HELLO = [HumanMessage("hi")]

# Values only need to satisfy ``Settings`` validation (non-empty DB/Redis URLs and a
# 32-byte base64 encryption key); disabled-flag tests never connect.
_TEST_SETTINGS_ENV = {
    "ENCRYPTION_MASTER_KEY": "lmnZiTdYDe6qnwh5yiWxEBRCzEcA/VCxuwBHAhzWnok=",
    "DATABASE_URL": "postgresql+asyncpg://metis_app:***@localhost:5432/metis",
    "REDIS_URL": "redis://localhost:6379/15",
}


def _settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in _TEST_SETTINGS_ENV.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()


# ------------------------------------------------------------------ helpers


async def workspace_with_key_and_base_url(
    engine: AsyncEngine,
    sub: str = "ada",
    key: str = LLM_KEY,
    model: str = LLM_MODEL,
    base_url: str = "https://llm.example.com/v1",
) -> UUID:
    """A user's personal workspace with an LLM key saved at a custom base URL."""
    user_id = await create_user(engine, sub, f"{sub}@example.com", sub.title())
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = await auth.get_user(session, user_id)
        assert user is not None
        workspace = await identity.ensure_personal_workspace(session, user)
        owner = Membership(workspace=workspace, role=MemberRole.OWNER)
        await set_key(session, owner, ProviderKind.LLM, key, base_url, model)
        await session.commit()
    return workspace.id


def _gw(
    engine: AsyncEngine,
    workspace_id: UUID,
    sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
    run_id: UUID | None = None,
) -> LLMGateway:
    return LLMGateway(
        workspace_id,
        run_id or uuid4(),
        sessions=sessions,
        http_client=server.client(),
        flags=StaticProvider(os.environ),
    )


# -------------------------------------------------- master switch blocks all
async def test_llm_enabled_false_blocks_all_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_LLM_ENABLED", "false")
    gw = LLMGateway(uuid4(), uuid4(), flags=StaticProvider(os.environ))

    with pytest.raises(ProviderNotConfiguredError) as caught:
        await gw.chat_model(None, "interview")  # type: ignore[arg-type]

    assert caught.value.meta == {"provider": "llm", "reason": "kill_switch"}


# -------------------------------------------------- per-provider switches
@pytest.mark.parametrize(
    ("vendor", "base_url", "flag_env", "flag_value"),
    [
        ("openai", "https://api.openai.com/v1", "FF_LLM_OPENAI_ENABLED", "false"),
        ("anthropic", "https://api.anthropic.com", "FF_LLM_ANTHROPIC_ENABLED", "false"),
        (
            "google",
            "https://generativelanguage.googleapis.com/v1",
            "FF_LLM_GOOGLE_ENABLED",
            "false",
        ),
        ("local", "http://localhost:11434", "FF_LLM_LOCAL_ENABLED", "false"),
    ],
)
async def test_provider_flag_false_blocks_only_that_provider(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
    vendor: str,
    base_url: str,
    flag_env: str,
    flag_value: str,
) -> None:
    """Master on + individual provider off blocks only that provider."""
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_LLM_ENABLED", "true")
    monkeypatch.setenv(flag_env, flag_value)
    get_settings.cache_clear()

    workspace_id = await workspace_with_key_and_base_url(engine, sub=vendor, base_url=base_url)
    run_id = await make_run(engine, workspace_id)
    gw = _gw(engine, workspace_id, app_sessions, server, run_id)

    async with app_sessions() as session:
        with pytest.raises(ProviderNotConfiguredError) as caught:
            await gw.chat_model(session, "interview")
    assert caught.value.meta == {"provider": vendor, "reason": "kill_switch"}
    assert server.requests == []


async def test_provider_flag_true_allows_call(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
) -> None:
    """Master on + provider flag on allows the call."""
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_LLM_ENABLED", "true")
    monkeypatch.setenv("FF_LLM_OPENAI_ENABLED", "true")
    get_settings.cache_clear()

    workspace_id = await workspace_with_key_and_base_url(
        engine, sub="openai", base_url="https://api.openai.com/v1"
    )
    run_id = await make_run(engine, workspace_id)
    gw = _gw(engine, workspace_id, app_sessions, server, run_id)

    async with app_sessions() as session:
        model = await gw.chat_model(session, "interview")
    reply = await model.ainvoke(HELLO)
    assert reply.content == "hello"
    assert len(server.requests) == 1


# -------------------------------------------------- integration: switch without redeploy
async def test_provider_flags_switch_without_redeploy(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
) -> None:
    """Flipping FF_LLM_OPENAI_ENABLED between false and true toggles OpenAI access."""
    _settings_env(monkeypatch)
    workspace_id = await workspace_with_key_and_base_url(
        engine, sub="openai", base_url="https://api.openai.com/v1"
    )
    run_id = await make_run(engine, workspace_id)

    # Off: blocked
    monkeypatch.setenv("FF_LLM_ENABLED", "true")
    monkeypatch.setenv("FF_LLM_OPENAI_ENABLED", "false")
    get_settings.cache_clear()
    gw_off = _gw(engine, workspace_id, app_sessions, server, run_id)
    async with app_sessions() as session:
        with pytest.raises(ProviderNotConfiguredError) as caught:
            await gw_off.chat_model(session, "interview")
    assert caught.value.meta == {"provider": "openai", "reason": "kill_switch"}
    assert server.requests == []

    # On: allowed
    monkeypatch.setenv("FF_LLM_OPENAI_ENABLED", "true")
    get_settings.cache_clear()
    gw_on = _gw(engine, workspace_id, app_sessions, server, run_id)
    async with app_sessions() as session:
        model = await gw_on.chat_model(session, "interview")
    reply = await model.ainvoke(HELLO)
    assert reply.content == "hello"
    assert len(server.requests) == 1


# -------------------------------------------------- unknown vendor defaults to allowed
async def test_unknown_vendor_is_allowed_by_default(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
) -> None:
    """A base URL that maps to no known vendor is not blocked by provider flags."""
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_LLM_ENABLED", "true")
    monkeypatch.setenv("FF_LLM_OPENAI_ENABLED", "false")
    get_settings.cache_clear()

    # Unknown vendor host: not openai/anthropic/google/local
    workspace_id = await workspace_with_key_and_base_url(
        engine, sub="unknown", base_url="https://api.example.com/v1"
    )
    run_id = await make_run(engine, workspace_id)
    gw = _gw(engine, workspace_id, app_sessions, server, run_id)

    async with app_sessions() as session:
        model = await gw.chat_model(session, "interview")
    reply = await model.ainvoke(HELLO)
    assert reply.content == "hello"


# -------------------------------------------------- unset provider flag defaults to on
async def test_unset_provider_flag_allows_call(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
) -> None:
    """Master on and no ``FF_LLM_OPENAI_ENABLED`` at all: the call is allowed."""
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_LLM_ENABLED", "true")
    monkeypatch.delenv("FF_LLM_OPENAI_ENABLED", raising=False)

    workspace_id = await workspace_with_key_and_base_url(
        engine, sub="openai", base_url="https://api.openai.com/v1"
    )
    run_id = await make_run(engine, workspace_id)
    gw = _gw(engine, workspace_id, app_sessions, server, run_id)

    async with app_sessions() as session:
        model = await gw.chat_model(session, "interview")
    assert (await model.ainvoke(HELLO)).content == "hello"


# -------------------------------------------------- a live gateway re-checks the flag
async def test_flag_flipped_after_model_built_blocks_next_call(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
) -> None:
    """The cached model must not outlive the kill switch."""
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_LLM_ENABLED", "true")
    monkeypatch.setenv("FF_LLM_OPENAI_ENABLED", "true")

    workspace_id = await workspace_with_key_and_base_url(
        engine, sub="openai", base_url="https://api.openai.com/v1"
    )
    run_id = await make_run(engine, workspace_id)
    gw = LLMGateway(
        workspace_id,
        run_id,
        sessions=app_sessions,
        http_client=server.client(),
        flags=_LiveEnvFlags(),
    )
    async with app_sessions() as session:
        await gw.chat_model(session, "interview")
        monkeypatch.setenv("FF_LLM_OPENAI_ENABLED", "false")
        with pytest.raises(ProviderNotConfiguredError) as caught:
            await gw.chat_model(session, "interview")
    assert caught.value.meta == {"provider": "openai", "reason": "kill_switch"}


class _LiveEnvFlags(StaticProvider):
    """A ``StaticProvider`` that re-reads the process env on every call."""

    def __init__(self) -> None:
        super().__init__(os.environ)

    async def is_enabled(self, key: str, context: FlagContext, default: bool = False) -> bool:
        return await StaticProvider(os.environ).is_enabled(key, context, default)


# -------------------------------------------------- base URL to vendor mapping
@pytest.mark.parametrize(
    ("base_url", "vendor"),
    [
        ("https://api.openai.com/v1", "openai"),
        ("https://api.anthropic.com", "anthropic"),
        ("https://generativelanguage.googleapis.com/v1", "google"),
        ("http://localhost:11434", "local"),
        ("http://[::1]:11434", "local"),
        ("https://openai.attacker.example/v1", None),
        ("https://my-resource.openai.azure.com", None),
        ("https://api.example.com/v1", None),
        ("http://[::1", None),
        ("", None),
        (None, None),
    ],
)
def test_vendor_from_base_url(base_url: str | None, vendor: str | None) -> None:
    assert _vendor_from_base_url(base_url) == vendor
