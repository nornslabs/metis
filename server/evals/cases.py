"""Eval cases: one JSON object per line of ``scoring/cases.jsonl``, validated on load.

A case freezes everything the Scorer reads (idea text, interview brief and answers, research
snapshot) and what a good verdict looks like (band, optional total range, per-parameter
ranges). A bad line stops the run with its line number, before any model call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from metis.modules.ideas import InterviewFindings
from metis.modules.scoring import ScoreBand, ScoreParam

CASES_PATH = Path(__file__).parent / "scoring" / "cases.jsonl"
MAX_MARK = 10
MAX_TOTAL = 100
# Total ranges of each band (the scoring module's own cut-offs: 75 and 55).
BAND_TOTALS: dict[ScoreBand, tuple[int, int]] = {
    ScoreBand.BUILD: (75, MAX_TOTAL),
    ScoreBand.PROMISING: (55, 74),
    ScoreBand.ADVISE: (0, 54),
}

CaseId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=60)]
Range = tuple[int, int]
SOURCED_KINDS = ("competitor", "market_fact")


class CaseFileError(ValueError):
    """A case file that cannot be used; the message names the line."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CaseItem(_Frozen):
    """A sourced finding of the frozen research snapshot."""

    kind: Literal["competitor", "market_fact", "trend", "risk"]
    title: str = Field(min_length=1)
    url: str | None = None
    quote: str | None = None
    claim: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _sourced_kinds_cite_a_url(self) -> Self:
        if self.kind in SOURCED_KINDS and not self.url:
            raise ValueError(f"a {self.kind} item needs a url")
        return self


class CaseCompetitor(_Frozen):
    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    description: str | None = None
    pricing: str | None = None
    overlap: float = Field(ge=0, le=1)


class CaseSnapshot(_Frozen):
    summary: str | None = None
    items: tuple[CaseItem, ...] = ()
    competitors: tuple[CaseCompetitor, ...] = ()

    def urls(self) -> frozenset[str]:
        """Every source URL the Scorer is allowed to cite."""
        return frozenset(
            [c.url for c in self.competitors] + [i.url for i in self.items if i.url is not None]
        )


class CaseAnswer(_Frozen):
    """One interview turn the user answered."""

    topic: Literal["problem", "solution", "customer", "payment", "feasibility", "other"]
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class Expect(_Frozen):
    """What a good verdict looks like. ``params`` lists only the marks the case is firm about."""

    band: ScoreBand
    total: Range | None = None
    params: dict[ScoreParam, Range] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ranges_are_sane(self) -> Self:
        for name, (low, high) in self.params.items():
            _check_range(str(name), low, high, MAX_MARK)
        if self.total is not None:
            _check_range("total", *self.total, MAX_TOTAL)
            band_low, band_high = BAND_TOTALS[self.band]
            if self.total[0] < band_low or self.total[1] > band_high:
                raise ValueError(f"total {self.total} is outside the {self.band.value} band")
        return self


class Case(_Frozen):
    id: CaseId
    title: str = Field(min_length=3)
    idea_text: str = Field(min_length=10)
    brief: InterviewFindings
    answers: tuple[CaseAnswer, ...] = ()
    snapshot: CaseSnapshot | None = None
    expect: Expect


def load_cases(path: Path = CASES_PATH) -> tuple[Case, ...]:
    """Every case of the file, in file order; the first bad line raises ``CaseFileError``."""
    cases: list[Case] = []
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        case = _parse_line(path, number, line)
        if case.id in seen_ids:
            raise CaseFileError(f"{path.name}:{number}: duplicate case id {case.id!r}")
        if case.title in seen_titles:
            raise CaseFileError(f"{path.name}:{number}: duplicate case title {case.title!r}")
        seen_ids.add(case.id)
        seen_titles.add(case.title)
        cases.append(case)
    if not cases:
        raise CaseFileError(f"{path.name}: no cases")
    return tuple(cases)


def _parse_line(path: Path, number: int, line: str) -> Case:
    try:
        return Case.model_validate(json.loads(line))
    except json.JSONDecodeError as exc:
        raise CaseFileError(f"{path.name}:{number}: not JSON ({exc.msg})") from exc
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"])
        raise CaseFileError(f"{path.name}:{number}: {where}: {first['msg']}") from exc


def _check_range(name: str, low: int, high: int, ceiling: int) -> None:
    if not 0 <= low <= high <= ceiling:
        raise ValueError(f"{name} range {(low, high)} must satisfy 0 <= min <= max <= {ceiling}")
