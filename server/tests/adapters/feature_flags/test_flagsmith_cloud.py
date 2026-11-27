"""Opt-in check against a real Flagsmith test environment (set FLAGSMITH_TEST_ENVIRONMENT_KEY).

The environment must hold: ``it_bool`` (enabled), ``it_string`` (value ``hello``),
``it_json`` (value ``{"a": 1}``) and a multivariate ``it_variant``.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from metis.adapters.feature_flags.flagsmith import FlagsmithProvider
from metis.core.config import AppSettings
from metis.core.ports import FlagContext

KEY = os.environ.get("FLAGSMITH_TEST_ENVIRONMENT_KEY")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not KEY, reason="FLAGSMITH_TEST_ENVIRONMENT_KEY is not set"),
]


async def test_real_environment_serves_boolean_string_json_and_variants() -> None:
    assert KEY is not None
    provider = FlagsmithProvider(KEY, AppSettings.DEFAULT_FLAGSMITH_API_URL)
    context = FlagContext(environment="integration-test")
    try:
        assert await provider.is_enabled("it_bool", context) is True
        assert await provider.get_string("it_string", context, "") == "hello"
        assert await provider.get_json("it_json", context, None) == {"a": 1}
        assert await provider.get_string("it_variant", context, "") != ""
    finally:
        await provider.close()


async def test_real_environment_serves_a_stable_variation_and_accepts_a_conversion() -> None:
    assert KEY is not None
    provider = FlagsmithProvider(KEY, AppSettings.DEFAULT_FLAGSMITH_API_URL)
    context = FlagContext(environment="integration-test", workspace_id=uuid4())
    try:
        first = await provider.get_experiment_variant("model_routing_strategy", context, "")
        again = await provider.get_experiment_variant("model_routing_strategy", context, "")
        assert first in {"cost_optimized", "quality_optimized", "balanced"}
        assert again == first
        await provider.track_event("run_completed_successfully", context)
    finally:
        await provider.close()
