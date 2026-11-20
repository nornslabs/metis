"""The pure checks on one stored score run, and the variance between repeated runs.

A check fails a run; a variance flag only reports. Nothing here touches a database or a model.
"""

from __future__ import annotations

from collections.abc import Sequence

from evals.cases import Case
from metis.agent.tools.scoring import normalize_url
from metis.modules.scoring import NO_EVIDENCE_MAX_CONFIDENCE, ScoreParam, ScoreParamResult, ScoreRun

MAX_MARK_SPREAD = 1


def check_run(case: Case, score: ScoreRun) -> tuple[str, ...]:
    """Why ``score`` is not a good verdict for ``case``; empty when it is."""
    failures: list[str] = []
    if score.band is not case.expect.band:
        failures.append(f"band {score.band.value}, expected {case.expect.band.value}")
    if case.expect.total is not None and not _within(score.total, case.expect.total):
        failures.append(f"total {score.total} outside {_span(case.expect.total)}")
    by_param = {p.param: p for p in score.params}
    for name, bounds in case.expect.params.items():
        result = by_param.get(name)
        if result is None:
            failures.append(f"{name.value} missing")
        elif not _within(result.raw, bounds):
            failures.append(f"{name.value} {result.raw} outside {_span(bounds)}")
    allowed = _normalized(case.snapshot.urls()) if case.snapshot is not None else frozenset()
    for result in score.params:
        failures.extend(_evidence_failures(result, allowed))
    return tuple(failures)


def unstable_flags(runs: Sequence[ScoreRun]) -> tuple[str, ...]:
    """Flags for a band that changed, or a mark that moved more than ``MAX_MARK_SPREAD``."""
    if len(runs) < 2:
        return ()
    flags: list[str] = []
    if len({run.band for run in runs}) > 1:
        flags.append("band changed between runs")
    for name in ScoreParam:
        marks = [p.raw for run in runs for p in run.params if p.param is name]
        if marks and max(marks) - min(marks) > MAX_MARK_SPREAD:
            flags.append(f"{name.value} unstable ({min(marks)}-{max(marks)})")
    return tuple(flags)


def _evidence_failures(result: ScoreParamResult, allowed: frozenset[str]) -> list[str]:
    name = result.param.value
    failures: list[str] = []
    if not result.reason.strip():
        failures.append(f"{name} has no reason")
    if result.no_evidence:
        if result.evidence or result.confidence > NO_EVIDENCE_MAX_CONFIDENCE:
            failures.append(f"{name} says no evidence but cites sources or is confident")
        return failures
    if not result.evidence:
        failures.append(f"{name} has no evidence")
    failures.extend(
        f"{name} cites {item.url}, not a source of the research"
        for item in result.evidence
        if normalize_url(item.url) not in allowed
    )
    return failures


def _normalized(urls: frozenset[str]) -> frozenset[str]:
    return frozenset(normalize_url(url) for url in urls)


def _within(value: int, bounds: tuple[int, int]) -> bool:
    return bounds[0] <= value <= bounds[1]


def _span(bounds: tuple[int, int]) -> str:
    return f"{bounds[0]}-{bounds[1]}"
