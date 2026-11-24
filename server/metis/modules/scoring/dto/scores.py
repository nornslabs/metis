"""Score DTOs: what the Scorer submits, and the stored score runs, views and diffs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field, model_validator

from metis.helpers.dto import FrozenModel
from metis.modules.scoring.dto._fields import Fraction, Mark, Quote, Reason, Title, WebUrl
from metis.modules.scoring.dto.enums import ScoreBand, ScoreParam, ScoreTrigger

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

MAX_EVIDENCE_ITEMS = 5
# With no evidence a score is a guess, so its confidence is at most this.
NO_EVIDENCE_MAX_CONFIDENCE = 0.30


class NewEvidence(FrozenModel):
    """One source behind a parameter's mark."""

    url: WebUrl
    title: Title
    quote: Quote = ""


class NewParamScore(FrozenModel):
    """One parameter's mark as the Scorer submits it; cross-field rules run at submission."""

    param: ScoreParam
    raw: Mark
    reason: Reason
    confidence: Fraction
    evidence: tuple[NewEvidence, ...] = Field(default=(), max_length=MAX_EVIDENCE_ITEMS)
    no_evidence: bool = False


class ScoreSubmission(FrozenModel):
    """All six parameters of one score. Refuses a missing, unknown or duplicate parameter."""

    params: tuple[NewParamScore, ...]

    @model_validator(mode="after")
    def _check_params(self) -> ScoreSubmission:
        seen: set[ScoreParam] = set()
        for entry in self.params:
            if entry.param in seen:
                raise ValueError(f"{entry.param.value} is given twice")
            seen.add(entry.param)
            _check_evidence(entry)
        missing = [p.value for p in ScoreParam if p not in seen]
        if missing:
            raise ValueError(f"missing parameters: {', '.join(missing)}")
        return self


class Rubric(FrozenModel):
    """A rubric version: the weight of each parameter (they sum to 100)."""

    version: int
    weights: dict[ScoreParam, int]


class EvidenceItem(FrozenModel):
    """A stored source."""

    url: str
    title: str
    quote: str


class ScoreParamResult(FrozenModel):
    """One stored parameter result, with the weight it was computed with."""

    param: ScoreParam
    weight: int
    raw: int
    weighted: float
    reason: str
    confidence: float
    no_evidence: bool
    evidence: tuple[EvidenceItem, ...]


class ScoreRunSummary(FrozenModel):
    """A score run without its parameters (history rows)."""

    id: UUID
    idea_id: UUID
    run_id: UUID
    rubric_version: int
    trigger: ScoreTrigger
    total: int
    band: ScoreBand
    created_at: datetime


class IdeaScoreSummary(FrozenModel):
    """One idea's score trend: run totals oldest first and the newest run's band."""

    idea_id: UUID
    band: ScoreBand
    totals: tuple[int, ...]


class IdeaScoreSummaryList(FrozenModel):
    """Summaries of the scored ideas among those asked for (any order)."""

    items: tuple[IdeaScoreSummary, ...]


class ScoreRun(ScoreRunSummary):
    """A score run with the rubric weights and its six parameters, in rubric order."""

    weights: dict[ScoreParam, int]
    params: tuple[ScoreParamResult, ...]


class ScoreHistory(FrozenModel):
    """An idea's score runs, newest first."""

    items: tuple[ScoreRunSummary, ...]


class ParamDiff(FrozenModel):
    """How one parameter moved from run A to run B (``B − A``)."""

    param: ScoreParam
    raw_delta: int
    weighted_delta: float
    confidence_delta: float


class ScoreDiff(FrozenModel):
    """Run B compared with run A of the same idea."""

    from_id: UUID
    to_id: UUID
    total_delta: int
    band_changed: bool
    params: tuple[ParamDiff, ...]


def _check_evidence(entry: NewParamScore) -> None:
    name = entry.param.value
    if entry.evidence and entry.no_evidence:
        raise ValueError(f"{name}: no_evidence is set but evidence is given")
    if not entry.evidence and not entry.no_evidence:
        raise ValueError(f"{name}: give evidence, or set no_evidence")
    if entry.no_evidence and entry.confidence > NO_EVIDENCE_MAX_CONFIDENCE:
        raise ValueError(
            f"{name}: confidence is at most {NO_EVIDENCE_MAX_CONFIDENCE} without evidence"
        )
