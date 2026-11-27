"""Simulate 100+ planning runs across the ``model_routing_strategy`` experiment variations.

Uses ``StaticProvider`` in CI / local mode (default) and ``FlagsmithProvider`` when
``--provider flagsmith`` or ``FEATURE_FLAG_PROVIDER=flagsmith`` is configured.

    cd server
    uv run python scripts/simulate_experiment.py --provider static --runs 120
    FEATURE_FLAG_PROVIDER=flagsmith FLAGSMITH_ENVIRONMENT_KEY=ser.xxx \\
        uv run python scripts/simulate_experiment.py --provider flagsmith --runs 120
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from uuid import UUID

from metis.adapters.feature_flags import (
    StaticProvider,
    build_feature_flag_provider,
    close_feature_flag_providers,
)
from metis.core.config import Settings
from metis.core.ports import FeatureFlagProvider, FlagContext

ROUTING_STRATEGY_FLAG = "model_routing_strategy"
ORDERED_STRATEGIES: tuple[str, ...] = ("cost_optimized", "quality_optimized", "balanced")
ROUTING_STRATEGIES = frozenset(ORDERED_STRATEGIES)
CONVERSION_EVENT = "run_completed_successfully"
DEFAULT_RUNS = 120

# Simulated completion rates per variation so Bayesian analysis identifies a clear winner.
SIMULATED_CONVERSION_RATES: dict[str, float] = {
    "cost_optimized": 0.62,
    "quality_optimized": 0.74,
    "balanced": 0.91,
}

DEFAULT_ROUTING_CONFIGS: dict[str, dict[str, str]] = {
    "cost_optimized": {
        "interviewer": "gpt-4o-mini",
        "researcher": "gpt-4o-mini",
        "scorer": "gpt-4o-mini",
        "planner": "gpt-4o-mini",
    },
    "quality_optimized": {
        "interviewer": "gpt-4o",
        "researcher": "gpt-4o",
        "scorer": "gpt-4o",
        "planner": "gpt-4o",
    },
    "balanced": {
        "interviewer": "gpt-4o-mini",
        "researcher": "gpt-4o-mini",
        "scorer": "gpt-4o",
        "planner": "gpt-4o",
    },
}


@dataclass(slots=True)
class VariationStats:
    """Observed exposures and conversions for one experiment variation."""

    exposures: int = 0
    conversions: int = 0
    sample_routing: dict[str, str] | None = None

    @property
    def conversion_rate(self) -> float:
        return 0.0 if self.exposures == 0 else self.conversions / self.exposures


@dataclass(slots=True)
class SimulationSummary:
    """Aggregate output of a simulated traffic run."""

    provider: str
    total_runs: int
    blocked_runs: int
    variations: dict[str, VariationStats]

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "total_runs": self.total_runs,
            "blocked_runs": self.blocked_runs,
            "variations": {
                name: {
                    **asdict(stats),
                    "conversion_rate": round(stats.conversion_rate, 4),
                }
                for name, stats in self.variations.items()
            },
        }


def _placeholder_settings(provider_kind: str) -> Settings:
    """Build Settings without requiring a full .env when running in static/CI mode."""
    env_overrides: dict[str, str] = {
        "DATABASE_URL": os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://placeholder:placeholder@localhost:5432/placeholder",
        ),
        "REDIS_URL": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        "ENCRYPTION_MASTER_KEY": os.environ.get(
            "ENCRYPTION_MASTER_KEY",
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        ),
        "FEATURE_FLAG_PROVIDER": provider_kind,
    }
    for key, value in env_overrides.items():
        os.environ.setdefault(key, value)
    return Settings()


def _static_providers_by_strategy() -> dict[str, StaticProvider]:
    """Build one StaticProvider per variation so CI exercises all 3 variations."""
    base_env = {k: v for k, v in os.environ.items() if k.startswith("FF_")}
    providers: dict[str, StaticProvider] = {}
    for strategy in ORDERED_STRATEGIES:
        env = {
            **base_env,
            "FF_MODEL_ROUTING_STRATEGY": strategy,
            f"FF_MODEL_ROUTING_{strategy.upper()}": json.dumps(DEFAULT_ROUTING_CONFIGS[strategy]),
        }
        providers[strategy] = StaticProvider(env)
    return providers


async def run_simulation(
    *,
    runs: int = DEFAULT_RUNS,
    provider_mode: str = "auto",
    seed: int = 42,
    provider_override: FeatureFlagProvider | None = None,
) -> SimulationSummary:
    """Run ``runs`` simulated planning workflows and return per-variation stats."""
    if runs < 1:
        raise ValueError("runs must be at least 1")

    settings = _placeholder_settings(
        "static" if provider_mode == "auto" and not os.environ.get("FEATURE_FLAG_PROVIDER") else (
            os.environ.get("FEATURE_FLAG_PROVIDER", "static")
            if provider_mode == "auto"
            else provider_mode
        )
    )
    resolved_mode = settings.feature_flag_provider if provider_mode == "auto" else provider_mode

    rng = random.Random(seed)
    stats: dict[str, VariationStats] = {name: VariationStats() for name in ORDERED_STRATEGIES}
    blocked_runs = 0

    static_pool: dict[str, StaticProvider] | None = None
    shared_provider: FeatureFlagProvider | None = provider_override

    if shared_provider is None:
        if resolved_mode == "static":
            if os.environ.get("FF_MODEL_ROUTING_STRATEGY"):
                shared_provider = build_feature_flag_provider(settings)
            else:
                static_pool = _static_providers_by_strategy()
        elif resolved_mode == "flagsmith":
            if settings.flagsmith_environment_key is None:
                raise ValueError(
                    "FLAGSMITH_ENVIRONMENT_KEY is required when using --provider flagsmith"
                )
            shared_provider = build_feature_flag_provider(settings)
        else:
            raise ValueError(f"Unsupported provider mode: {resolved_mode}")

    try:
        for idx in range(runs):
            workspace_id = UUID(int=rng.getrandbits(128))
            context = FlagContext(workspace_id=workspace_id, environment=settings.app_env)
            provider = (
                static_pool[ORDERED_STRATEGIES[idx % len(ORDERED_STRATEGIES)]]
                if static_pool is not None
                else shared_provider
            )
            assert provider is not None

            if not await provider.is_enabled("llm_enabled", context, default=True):
                blocked_runs += 1
                continue

            variant = await provider.get_experiment_variant(
                ROUTING_STRATEGY_FLAG, context, "balanced"
            )
            if variant not in ROUTING_STRATEGIES:
                variant = "balanced"

            routing_raw = await provider.get_json(
                f"model_routing_{variant}",
                context,
                DEFAULT_ROUTING_CONFIGS[variant],
            )
            routing = (
                {str(k): str(v) for k, v in routing_raw.items()}
                if isinstance(routing_raw, dict)
                else DEFAULT_ROUTING_CONFIGS[variant]
            )

            entry = stats[variant]
            entry.exposures += 1
            if entry.sample_routing is None:
                entry.sample_routing = routing

            rate = SIMULATED_CONVERSION_RATES.get(variant, 0.7)
            if rng.random() < rate:
                await provider.track_event(CONVERSION_EVENT, context)
                entry.conversions += 1
    finally:
        await close_feature_flag_providers()

    return SimulationSummary(
        provider=resolved_mode,
        total_runs=runs,
        blocked_runs=blocked_runs,
        variations=stats,
    )


def _format_table(summary: SimulationSummary) -> str:
    lines = [
        f"Provider: {summary.provider} | Total runs: {summary.total_runs} "
        f"| Blocked by kill switch: {summary.blocked_runs}",
        "-" * 72,
        f"{'Variation':<20} {'Exposures':>10} {'Conversions':>12} {'Conv Rate':>12}",
        "-" * 72,
    ]
    for name in ORDERED_STRATEGIES:
        s = summary.variations[name]
        lines.append(f"{name:<20} {s.exposures:>10} {s.conversions:>12} {s.conversion_rate:>11.1%}")
    lines.append("-" * 72)
    return "\n".join(lines)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate Metis planning runs across model_routing_strategy variations."
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help=f"Number of planning runs to simulate (default: {DEFAULT_RUNS}).",
    )
    parser.add_argument(
        "--provider",
        choices=("auto", "static", "flagsmith"),
        default="auto",
        help="Feature flag provider to use (default: auto).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic simulation (default: 42).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON instead of a table.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    summary = asyncio.run(
        run_simulation(runs=args.runs, provider_mode=args.provider, seed=args.seed)
    )
    if args.json:
        sys.stdout.write(json.dumps(summary.to_dict(), indent=2))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(_format_table(summary))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
