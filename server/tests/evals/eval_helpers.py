"""Builders for eval tests: a stored score run, and a case, without a database."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from evals.cases import Case, CaseSnapshot, Expect
from metis.modules.ideas import InterviewFindings
from metis.modules.scoring import (
    ScoreBand,
    ScoreParam,
    ScoreParamResult,
    ScoreRun,
    ScoreTrigger,
)
from metis.modules.scoring.dto.scores import EvidenceItem

WEIGHTS = {
    ScoreParam.PROBLEM_SEVERITY: 25,
    ScoreParam.UNIQUENESS: 25,
    ScoreParam.MARKET_DEMAND: 15,
    ScoreParam.VALUE: 15,
    ScoreParam.FEASIBILITY: 10,
    ScoreParam.TIMING: 10,
}
SOURCE = "https://reports.example.org/source"
OTHER = "https://made-up.example.net/data"


def param(
    name: ScoreParam,
    raw: int,
    *,
    url: str | None = SOURCE,
    no_evidence: bool = False,
    confidence: float = 0.7,
    reason: str = "Because the research says so.",
) -> ScoreParamResult:
    evidence = () if url is None or no_evidence else (EvidenceItem(url=url, title="T", quote="Q"),)
    return ScoreParamResult(
        param=name,
        weight=WEIGHTS[name],
        raw=raw,
        weighted=raw * WEIGHTS[name] / 10,
        reason=reason,
        confidence=confidence,
        no_evidence=no_evidence,
        evidence=evidence,
    )


def score_run(
    marks: dict[ScoreParam, int] | None = None,
    *,
    band: ScoreBand = ScoreBand.PROMISING,
    total: int = 60,
    overrides: dict[ScoreParam, ScoreParamResult] | None = None,
) -> ScoreRun:
    chosen = marks or dict.fromkeys(ScoreParam, 6)
    params = {name: param(name, raw) for name, raw in chosen.items()}
    params.update(overrides or {})
    return ScoreRun(
        id=uuid4(),
        idea_id=uuid4(),
        run_id=uuid4(),
        rubric_version=1,
        trigger=ScoreTrigger.MANUAL,
        total=total,
        band=band,
        created_at=datetime.now(UTC),
        weights=WEIGHTS,
        params=tuple(params[name] for name in ScoreParam if name in params),
    )


def case(
    *,
    band: ScoreBand = ScoreBand.PROMISING,
    total: tuple[int, int] | None = None,
    params: dict[ScoreParam, tuple[int, int]] | None = None,
    snapshot: CaseSnapshot | None = None,
) -> Case:
    expect: dict[str, Any] = {"band": band, "total": total, "params": params or {}}
    return Case(
        id="a-case",
        title="A case title",
        idea_text="An idea that is long enough.",
        brief=InterviewFindings(),
        snapshot=snapshot
        or CaseSnapshot.model_validate(
            {
                "competitors": [],
                "items": [
                    {
                        "kind": "market_fact",
                        "title": "T",
                        "url": SOURCE,
                        "claim": "C",
                        "confidence": 0.5,
                    }
                ],
            }
        ),
        expect=Expect.model_validate(expect),
    )
