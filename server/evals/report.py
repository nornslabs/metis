"""What one eval run produced, and the plain-text report a developer reads."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from metis.modules.scoring import ScoreBand

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class RunOutcome:
    """One Scorer run of one case. ``band`` is ``None`` when the run stored no score."""

    band: ScoreBand | None
    total: int | None
    failures: tuple[str, ...]
    error_code: str | None = None

    @property
    def passed(self) -> bool:
        return self.band is not None and not self.failures


@dataclass(frozen=True)
class CaseOutcome:
    case_id: str
    expected_band: ScoreBand
    runs: tuple[RunOutcome, ...]
    flags: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return all(run.passed for run in self.runs)


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal | None


def combine_usage(items: Sequence[Usage]) -> Usage:
    """The sum of ``items``; the cost is unknown when any item's is."""
    costs = [u.cost_usd for u in items if u.cost_usd is not None]
    known = len(costs) == len(items)
    return Usage(
        input_tokens=sum(u.input_tokens for u in items),
        output_tokens=sum(u.output_tokens for u in items),
        cost_usd=sum(costs, Decimal(0)) if known else None,
    )


def results_as_json(
    outcomes: Sequence[CaseOutcome], *, model: str, prompt: str
) -> dict[str, object]:
    """The run's results as plain data for ``--json``."""
    return {
        "model": model,
        "prompt": prompt,
        "pass_rate": pass_rate(outcomes),
        "cases": [
            {
                "id": o.case_id,
                "expected_band": o.expected_band.value,
                "passed": o.passed,
                "flags": list(o.flags),
                "runs": [
                    {
                        "band": r.band.value if r.band else None,
                        "total": r.total,
                        "failures": list(r.failures),
                        "error_code": r.error_code,
                    }
                    for r in o.runs
                ],
            }
            for o in outcomes
        ],
    }


def pass_rate(outcomes: Sequence[CaseOutcome]) -> float:
    return sum(o.passed for o in outcomes) / len(outcomes) if outcomes else 0.0


def band_accuracy(outcomes: Sequence[CaseOutcome]) -> float:
    runs = [(o.expected_band, run) for o in outcomes for run in o.runs]
    return sum(run.band is band for band, run in runs) / len(runs) if runs else 0.0


def format_report(
    outcomes: Sequence[CaseOutcome], *, model: str, prompt: str, usage: Usage | None
) -> str:
    """The table, the failures, then the totals."""
    width = max((len(o.case_id) for o in outcomes), default=4)
    lines = [f"{'case':<{width}}  {'expect':<9}  {'got':<22}  {'total':<9}  result"]
    for outcome in outcomes:
        lines.append(_row(outcome, width))
    failing = [o for o in outcomes if not o.passed]
    if failing:
        lines += ["", "Failures:"]
        lines += [f"  {o.case_id}: {reason}" for o in failing for reason in _reasons(o)]
    flagged = [o for o in outcomes if o.flags]
    if flagged:
        lines += ["", "Unstable:"]
        lines += [f"  {o.case_id}: {flag}" for o in flagged for flag in o.flags]
    passed = sum(o.passed for o in outcomes)
    lines += [
        "",
        f"Pass rate: {passed}/{len(outcomes)} = {pass_rate(outcomes):.0%}",
        f"Band accuracy: {band_accuracy(outcomes):.0%}",
        f"Unstable cases: {len(flagged)}",
        f"Prompt: {prompt}   Model: {model}",
    ]
    if usage is not None:
        cost = "unknown" if usage.cost_usd is None else f"${usage.cost_usd:.4f}"
        lines.append(f"Tokens: {usage.input_tokens} in / {usage.output_tokens} out   Cost: {cost}")
    return "\n".join(lines)


def _row(outcome: CaseOutcome, width: int) -> str:
    got = " / ".join(run.band.value if run.band else "none" for run in outcome.runs)
    totals = " / ".join("-" if run.total is None else str(run.total) for run in outcome.runs)
    verdict = "PASS" if outcome.passed else "FAIL"
    if outcome.flags:
        verdict += " (unstable)"
    return (
        f"{outcome.case_id:<{width}}  {outcome.expected_band.value:<9}  {got:<22}  "
        f"{totals:<9}  {verdict}"
    )


def _reasons(outcome: CaseOutcome) -> list[str]:
    reasons: list[str] = []
    for number, run in enumerate(outcome.runs, start=1):
        if run.error_code is not None:
            reasons.append(f"run {number}: no score stored ({run.error_code})")
        reasons.extend(f"run {number}: {failure}" for failure in run.failures)
    return reasons
