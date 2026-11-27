"""Feature flag adapters: ``StaticProvider`` (env vars), ``FlagsmithProvider`` and the factory."""

from __future__ import annotations

import os
from collections.abc import Mapping

from metis.adapters.feature_flags.flagsmith import FlagsmithProvider
from metis.adapters.feature_flags.static import StaticProvider
from metis.core.config import Settings
from metis.core.ports import FeatureFlagProvider

# One Flagsmith provider per (key, url): each owns a refresh thread and callers build freely.
_flagsmith_providers: dict[tuple[str, str], FlagsmithProvider] = {}


def build_feature_flag_provider(
    settings: Settings, environ: Mapping[str, str] | None = None
) -> FeatureFlagProvider:
    """The provider for ``settings.feature_flag_provider``.

    ``static`` reads ``FF_*`` from ``environ`` (the process environment by default).
    ``flagsmith`` returns the shared provider for the configured key and URL.
    """
    if settings.feature_flag_provider == "static":
        return StaticProvider(os.environ if environ is None else environ)
    if settings.flagsmith_environment_key is None:
        raise ValueError("flagsmith_environment_key is required when using flagsmith")
    key = settings.flagsmith_environment_key.get_secret_value()
    cache_key = (key, settings.flagsmith_api_url)
    provider = _flagsmith_providers.get(cache_key)
    if provider is None:
        provider = FlagsmithProvider(key, settings.flagsmith_api_url)
        _flagsmith_providers[cache_key] = provider
    return provider


async def close_feature_flag_providers() -> None:
    """Stop every shared provider (call at process shutdown) and forget them."""
    providers = list(_flagsmith_providers.values())
    _flagsmith_providers.clear()
    for provider in providers:
        await provider.close()


__all__ = [
    "FlagsmithProvider",
    "StaticProvider",
    "build_feature_flag_provider",
    "close_feature_flag_providers",
]
