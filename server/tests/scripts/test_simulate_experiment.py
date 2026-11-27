"""Tests for the experiment traffic simulation script."""

from __future__ import annotations

import pytest

from metis.adapters.feature_flags import StaticProvider
from scripts.simulate_experiment import ORDERED_STRATEGIES, run_simulation


async def test_run_simulation_static_exercises_all_three_variations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FF_MODEL_ROUTING_STRATEGY", raising=False)
    monkeypatch.delenv("FF_LLM_ENABLED", raising=False)

    summary = await run_simulation(runs=120, provider_mode="static", seed=7)

    assert summary.provider == "static"
    assert summary.total_runs == 120
    assert summary.blocked_runs == 0
    for strategy in ORDERED_STRATEGIES:
        stats = summary.variations[strategy]
        assert stats.exposures == 40
        assert 0 < stats.conversions <= stats.exposures
        assert stats.sample_routing is not None


async def test_run_simulation_respects_llm_enabled_kill_switch() -> None:
    provider = StaticProvider({"FF_LLM_ENABLED": "false"})

    summary = await run_simulation(runs=15, provider_mode="static", provider_override=provider)

    assert summary.total_runs == 15
    assert summary.blocked_runs == 15
    assert all(s.exposures == 0 for s in summary.variations.values())
