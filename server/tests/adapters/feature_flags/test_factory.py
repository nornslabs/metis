"""build_feature_flag_provider: provider selection from settings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from metis.adapters.feature_flags import (
    FlagsmithProvider,
    StaticProvider,
    build_feature_flag_provider,
    close_feature_flag_providers,
)
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


def _flagsmith_settings(key: str = "ser.test-key") -> Settings:
    return Settings(feature_flag_provider="flagsmith", flagsmith_environment_key=key)


async def test_flagsmith_returns_one_shared_provider_until_closed() -> None:
    first = build_feature_flag_provider(_flagsmith_settings())
    second = build_feature_flag_provider(_flagsmith_settings())

    assert isinstance(first, FlagsmithProvider)
    assert first is second

    await close_feature_flag_providers()
    third = build_feature_flag_provider(_flagsmith_settings())

    assert third is not first
    await close_feature_flag_providers()


async def test_a_closed_shared_provider_returns_defaults() -> None:
    provider = build_feature_flag_provider(_flagsmith_settings())

    await close_feature_flag_providers()

    assert await provider.is_enabled("llm_enabled", FlagContext(environment="test"), True) is True


def test_a_client_side_key_is_refused_without_printing_it() -> None:
    with pytest.raises(ValidationError) as error:
        _flagsmith_settings("client-side-secret")

    assert "client-side-secret" not in str(error.value)
