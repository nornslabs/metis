"""Feature flag adapters: ``StaticProvider`` (env vars) and the factory that picks a provider."""

from __future__ import annotations

import os
from collections.abc import Mapping

from metis.adapters.feature_flags.static import StaticProvider
from metis.core.config import Settings
from metis.core.ports import FeatureFlagProvider


def build_feature_flag_provider(
    settings: Settings, environ: Mapping[str, str] | None = None
) -> FeatureFlagProvider:
    """The provider for ``settings.feature_flag_provider``.

    ``static`` reads ``FF_*`` from ``environ`` (the process environment by default).
    """
    if settings.feature_flag_provider == "static":
        return StaticProvider(os.environ if environ is None else environ)
    raise ValueError("Flagsmith provider is not available yet")


__all__ = ["StaticProvider", "build_feature_flag_provider"]
