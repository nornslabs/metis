"""build_feature_flag_provider: provider selection from settings."""

from __future__ import annotations

import pytest

from metis.adapters.feature_flags import StaticProvider, build_feature_flag_provider
from metis.core.config import Settings
from metis.core.ports import FlagContext


async def test_static_provider_is_selected_and_fed_from_the_given_environment() -> None:
    settings = Settings(feature_flag_provider="static")

    provider = build_feature_flag_provider(settings, {"FF_LLM_ENABLED": "true"})

    assert isinstance(provider, StaticProvider)
    assert await provider.is_enabled("llm_enabled", FlagContext(environment="test")) is True


async def test_static_provider_is_the_default_and_reads_the_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FF_LLM_ENABLED", "true")

    provider = build_feature_flag_provider(Settings())

    assert isinstance(provider, StaticProvider)
    assert await provider.is_enabled("llm_enabled", FlagContext(environment="test")) is True


def test_flagsmith_is_not_available_until_its_provider_exists() -> None:
    settings = Settings(feature_flag_provider="flagsmith", flagsmith_environment_key="env-key")

    with pytest.raises(ValueError, match="not available yet"):
        build_feature_flag_provider(settings)
