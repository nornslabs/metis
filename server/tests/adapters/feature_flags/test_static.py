"""StaticProvider: flags from ``FF_*`` env values."""

from __future__ import annotations

import pytest
import structlog

from metis.adapters.feature_flags import StaticProvider
from metis.core.ports import FlagContext

CONTEXT = FlagContext(environment="test")


@pytest.mark.parametrize("raw", ["true", "TRUE", " True ", "1", "yes", "on"])
async def test_is_enabled_reads_true_spellings(raw: str) -> None:
    provider = StaticProvider({"FF_LLM_ENABLED": raw})

    assert await provider.is_enabled("llm_enabled", CONTEXT) is True


@pytest.mark.parametrize("raw", ["false", "FALSE", " off ", "0", "no"])
async def test_is_enabled_reads_false_spellings_over_a_true_default(raw: str) -> None:
    provider = StaticProvider({"FF_LLM_ENABLED": raw})

    assert await provider.is_enabled("llm_enabled", CONTEXT, default=True) is False


@pytest.mark.parametrize("values", [{}, {"FF_LLM_ENABLED": ""}, {"FF_LLM_ENABLED": "  "}])
async def test_is_enabled_returns_the_default_when_unset_or_empty(values: dict[str, str]) -> None:
    provider = StaticProvider(values)

    assert await provider.is_enabled("llm_enabled", CONTEXT) is False
    assert await provider.is_enabled("llm_enabled", CONTEXT, default=True) is True


async def test_is_enabled_returns_the_default_and_warns_once_for_a_malformed_value() -> None:
    provider = StaticProvider({"FF_LLM_ENABLED": "maybe"})

    with structlog.testing.capture_logs() as logs:
        first = await provider.is_enabled("llm_enabled", CONTEXT, default=True)
        second = await provider.is_enabled("llm_enabled", CONTEXT, default=True)

    assert first is True and second is True
    assert [entry["event"] for entry in logs] == ["feature_flags.invalid_value"]
    assert "maybe" not in str(logs)


async def test_get_string_returns_the_trimmed_value_or_the_default() -> None:
    provider = StaticProvider({"FF_REGION": " eu ", "FF_EMPTY": ""})

    assert await provider.get_string("region", CONTEXT, "us") == "eu"
    assert await provider.get_string("empty", CONTEXT, "us") == "us"
    assert await provider.get_string("missing", CONTEXT, "us") == "us"


async def test_get_json_parses_objects_and_lists() -> None:
    provider = StaticProvider(
        {
            "FF_MODEL_ROUTING": '{"spec": "big-model"}',
            "FF_CAPABILITIES": '["research", "export"]',
        }
    )

    assert await provider.get_json("model_routing", CONTEXT, {}) == {"spec": "big-model"}
    assert await provider.get_json("capabilities", CONTEXT, []) == ["research", "export"]


async def test_get_json_returns_the_default_when_unset_or_invalid() -> None:
    provider = StaticProvider({"FF_RATE_LIMITS": "{not json"})
    default = {"per_minute": 10}

    with structlog.testing.capture_logs() as logs:
        invalid = await provider.get_json("rate_limits", CONTEXT, default)
    missing = await provider.get_json("model_routing", CONTEXT, default)

    assert invalid == default and missing == default
    assert [entry["event"] for entry in logs] == ["feature_flags.invalid_value"]


async def test_only_ff_prefixed_values_are_read() -> None:
    provider = StaticProvider({"LLM_ENABLED": "true", "PATH": "/bin"})

    assert await provider.is_enabled("llm_enabled", CONTEXT) is False
    assert await provider.get_string("path", CONTEXT, "none") == "none"


async def test_every_context_sees_the_same_value() -> None:
    provider = StaticProvider({"FF_LLM_ENABLED": "true"})
    other = FlagContext(environment="prod", custom_attributes={"plan": "pro"})

    assert await provider.is_enabled("llm_enabled", other) is True


async def test_close_can_be_awaited_twice() -> None:
    provider = StaticProvider({})

    await provider.close()
    await provider.close()


async def test_experiment_variant_reads_the_env_var_and_defaults_when_unset() -> None:
    context = FlagContext(environment="test")
    configured = StaticProvider({"FF_MODEL_ROUTING_STRATEGY": "balanced"})
    unset = StaticProvider({})

    assert (
        await configured.get_experiment_variant("model_routing_strategy", context, "") == "balanced"
    )
    assert await unset.get_experiment_variant("model_routing_strategy", context, "") == ""


async def test_track_event_is_a_no_op_that_never_raises() -> None:
    await StaticProvider({}).track_event("run_completed_successfully", FlagContext("test"))
