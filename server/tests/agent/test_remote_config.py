"""JSON remote config tests: model routing, rate limits, capabilities, and overrides.

Tests cover the StaticProvider ``get_json`` method and its consumers:
``LLMGateway.chat_model()`` (model routing + rate limits) and the workspace settings
service (capabilities, run_budget_usd, max_steps overrides).
"""

from __future__ import annotations

import os
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.adapters.feature_flags import StaticProvider
from metis.agent.llm import LLMGateway
from metis.core.config import get_settings
from metis.core.errors import ProviderNotConfiguredError
from metis.core.ports import FlagContext
from metis.modules.identity import get_settings_overview
from tests.agent.llm_helpers import (
    FakeLLMServer,
    make_run,
    workspace_with_key,
)

# Values only need to satisfy ``Settings`` validation.
_TEST_SETTINGS_ENV = {
    "ENCRYPTION_MASTER_KEY": "lmnZiTdYDe6qnwh5yiWxEBRCzEcA/VCxuwBHAhzWnok=",
    "DATABASE_URL": "postgresql+asyncpg://metis_app:test@localhost:5432/metis",
    "REDIS_URL": "redis://localhost:6379/15",
}


def _settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in _TEST_SETTINGS_ENV.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()


def _flag_context(workspace_id: UUID | None = None, tier: str = "default") -> FlagContext:
    return FlagContext(
        workspace_id=workspace_id or uuid4(),
        environment="test",
        custom_attributes={"tier": tier},
    )


# ------------------------------------------------------------- StaticProvider.get_json
@pytest.mark.parametrize(
    ("flag", "env_value", "expected"),
    [
        (
            "model_routing",
            '{"free": "small", "default": "medium"}',
            {"free": "small", "default": "medium"},
        ),
        (
            "rate_limits",
            '{"free": {"requests_per_minute": 5}}',
            {"free": {"requests_per_minute": 5}},
        ),
        ("capabilities", '{"voice_input": true}', {"voice_input": True}),
        ("model_routing", None, {}),
        ("rate_limits", None, {}),
        ("capabilities", None, {}),
        ("model_routing", "not json", {}),
    ],
)
async def test_static_provider_get_json(
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
    env_value: str | None,
    expected: dict[str, object],
) -> None:
    _settings_env(monkeypatch)
    if env_value is not None:
        monkeypatch.setenv(f"FF_{flag.upper()}", env_value)
    else:
        monkeypatch.delenv(f"FF_{flag.upper()}", raising=False)
    provider = StaticProvider(os.environ)
    assert await provider.get_json(flag, _flag_context(), {}) == expected


# ------------------------------------------------------------- LLMGateway model routing
@pytest.mark.parametrize(
    ("tier", "routing", "expected_model"),
    [
        ("free", {"free": "small-model", "default": "medium-model"}, "small-model"),
        ("standard", {"standard": "med-model", "default": "medium-model"}, "med-model"),
        ("premium", {"premium": "large-model", "default": "medium-model"}, "large-model"),
        ("internal", {"internal": "internal-model", "default": "medium-model"}, "internal-model"),
        ("unknown", {"default": "medium-model"}, "medium-model"),
        ("unknown", {"fallback": "fallback-model"}, "fallback-model"),
        ("unknown", {}, "test-model"),
    ],
)
async def test_model_routing_selects_model_for_tier(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
    tier: str,
    routing: dict[str, str],
    expected_model: str,
) -> None:
    _settings_env(monkeypatch)
    import json

    monkeypatch.setenv("FF_MODEL_ROUTING", json.dumps(routing))
    get_settings.cache_clear()

    workspace_id = await workspace_with_key(engine)
    run_id = await make_run(engine, workspace_id)

    gw = LLMGateway(
        workspace_id,
        run_id,
        sessions=app_sessions,
        http_client=server.client(),
        flags=StaticProvider(os.environ),
    )

    async with app_sessions() as session:
        model = await gw.chat_model(session, "interview", tier=tier)

    assert model is not None
    reply = await model.ainvoke([HumanMessage("hi")])
    assert reply.content == "hello"
    request_body = server.requests[0].read().decode()
    assert f'"model":"{expected_model}"' in request_body


# ------------------------------------------------------------- LLMGateway rate limits
async def test_rate_limits_enforced_per_tier(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
) -> None:
    _settings_env(monkeypatch)
    import json

    monkeypatch.setenv("FF_RATE_LIMITS", json.dumps({"free": {"requests_per_minute": 2}}))
    get_settings.cache_clear()

    workspace_id = await workspace_with_key(engine)
    run_id = await make_run(engine, workspace_id)

    gw = LLMGateway(
        workspace_id,
        run_id,
        sessions=app_sessions,
        http_client=server.client(),
        flags=StaticProvider(os.environ),
    )

    async with app_sessions() as session:
        # First two calls succeed
        model = await gw.chat_model(session, "interview", tier="free")
        await model.ainvoke([HumanMessage("hi")])
        model = await gw.chat_model(session, "interview", tier="free")
        await model.ainvoke([HumanMessage("hi")])
        # Third call exceeds the limit
        with pytest.raises(ProviderNotConfiguredError) as caught:
            await gw.chat_model(session, "interview", tier="free")
        assert caught.value.meta == {
            "provider": "llm",
            "reason": "rate_limited",
            "tier": "free",
        }


async def test_rate_limits_independent_per_tier(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
    server: FakeLLMServer,
) -> None:
    _settings_env(monkeypatch)
    import json

    monkeypatch.setenv("FF_RATE_LIMITS", json.dumps({"premium": {"requests_per_minute": 1}}))
    get_settings.cache_clear()

    workspace_id = await workspace_with_key(engine)
    run_id = await make_run(engine, workspace_id)

    gw = LLMGateway(
        workspace_id,
        run_id,
        sessions=app_sessions,
        http_client=server.client(),
        flags=StaticProvider(os.environ),
    )

    async with app_sessions() as session:
        model = await gw.chat_model(session, "interview", tier="premium")
        await model.ainvoke([HumanMessage("hi")])
        # Second call for premium tier exceeds its limit of 1
        with pytest.raises(ProviderNotConfiguredError):
            await gw.chat_model(session, "interview", tier="premium")


# ------------------------------------------------------------- Settings remote config overrides
async def _save_settings(
    engine: AsyncEngine, workspace_id: UUID, budget: Decimal, steps: int
) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO identity.workspace_settings "
                "(workspace_id, run_budget_usd, max_steps) "
                "VALUES (:ws, :budget, :steps)"
            ),
            {"ws": workspace_id, "budget": budget, "steps": steps},
        )


async def test_settings_capabilities_from_flags(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    _settings_env(monkeypatch)
    monkeypatch.setenv(
        "FF_CAPABILITIES",
        '{"voice_input": true, "web_search": false, "code_execution": true, '
        '"market_watch": false, "notion_export": true}',
    )
    get_settings.cache_clear()

    workspace_id = await workspace_with_key(engine)

    async with app_sessions() as session:
        overview = await get_settings_overview(session, workspace_id)

    caps = overview.settings.capabilities
    assert caps["voice_input"] is True
    assert caps["web_search"] is False
    assert caps["code_execution"] is True
    assert caps["market_watch"] is False
    assert caps["notion_export"] is True


async def test_settings_run_budget_usd_override(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_RUN_BUDGET_USD", '{"value": 25.50}')
    get_settings.cache_clear()

    workspace_id = await workspace_with_key(engine)

    async with app_sessions() as session:
        await _save_settings(engine, workspace_id, Decimal("2.00"), 50)

    async with app_sessions() as session:
        overview = await get_settings_overview(session, workspace_id)

    assert overview.settings.run_budget_usd == Decimal("25.50")


async def test_settings_max_steps_override(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    _settings_env(monkeypatch)
    monkeypatch.setenv("FF_MAX_STEPS", '{"value": 200}')
    get_settings.cache_clear()

    workspace_id = await workspace_with_key(engine)

    async with app_sessions() as session:
        await _save_settings(engine, workspace_id, Decimal("2.00"), 50)

    async with app_sessions() as session:
        overview = await get_settings_overview(session, workspace_id)

    assert overview.settings.max_steps == 200


async def test_settings_flags_default_use_db_values(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    _settings_env(monkeypatch)
    # No FF_* env vars set -> flags return defaults (empty dicts)
    get_settings.cache_clear()

    workspace_id = await workspace_with_key(engine)

    async with app_sessions() as session:
        await _save_settings(engine, workspace_id, Decimal("42.00"), 77)

    async with app_sessions() as session:
        overview = await get_settings_overview(session, workspace_id)

    assert overview.settings.run_budget_usd == Decimal("42.00")
    assert overview.settings.max_steps == 77
    assert overview.settings.capabilities == {}
