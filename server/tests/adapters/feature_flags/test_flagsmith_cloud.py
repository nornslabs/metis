"""Opt-in check against a real Flagsmith test environment (set FLAGSMITH_TEST_ENVIRONMENT_KEY).

The environment must hold: ``it_bool`` (enabled), ``it_string`` (value ``hello``),
``it_json`` (value ``{"a": 1}``) and a multivariate ``it_variant``.
"""

from __future__ import annotations

import os

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
