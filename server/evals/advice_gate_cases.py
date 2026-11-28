"""Advisor gate eval cases: one JSON object per line of ``advice_gates/cases.jsonl``.

A case freezes a candidate suggestion with everything the gate reads (the idea, the weakest
score parameters with the score's reasons, the suggestions already saved, the URLs the run saw)
and the verdict it must get: ``pass`` (a strong suggestion is saved) or ``reject`` (a generic,
duplicate, wrong-target, unsourced or unsupported one is refused). A rejection says who rejects
it: ``code`` (a code check, no model call) or ``judge`` (a recorded or real model verdict).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from metis.modules.scoring import NewSuggestion, ScoreParam

CASES_PATH = Path(__file__).parent / "advice_gates" / "cases.jsonl"
RECORDED_PATH = Path(__file__).parent / "advice_gates" / "recorded.jsonl"

CaseId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=60)]
Expect = Literal["pass", "reject"]
RejectBy = Literal["code", "judge"]


class AdviceGateCaseFileError(ValueError):
    """A case file that cannot be used; the message names the line."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AdviceIdea(_Frozen):
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)


class AdviceWeakParam(_Frozen):
    param: ScoreParam
    raw: int = Field(ge=0, le=10)
    reason: str = Field(min_length=1)


class AdviceGateCase(_Frozen):
    id: CaseId
    idea: AdviceIdea
    weakest: tuple[AdviceWeakParam, ...] = Field(min_length=1)
    saved_titles: tuple[str, ...] = ()
    known_urls: tuple[str, ...] = Field(min_length=1)
    suggestion: NewSuggestion
    expect: Expect
    reject_by: RejectBy | None = None

    @model_validator(mode="after")
    def _reject_by_matches_expect(self) -> Self:
        if (self.expect == "reject") != (self.reject_by is not None):
            raise ValueError("reject_by is set exactly when expect is reject")
        return self


def load_advice_gate_cases(path: Path = CASES_PATH) -> tuple[AdviceGateCase, ...]:
    """The cases of ``path``; raises ``AdviceGateCaseFileError`` on a bad line or a repeat."""
    cases: list[AdviceGateCase] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(AdviceGateCase.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AdviceGateCaseFileError(f"{path.name} line {number}: {exc}") from exc
    if not cases:
        raise AdviceGateCaseFileError(f"{path.name}: no cases")
    for label, values in (
        ("id", [c.id for c in cases]),
        ("suggestion title", [c.suggestion.title for c in cases]),
    ):
        repeated = sorted({v for v in values if values.count(v) > 1})
        if repeated:
            raise AdviceGateCaseFileError(
                f"{path.name}: repeated case {label}(s): {', '.join(repeated)}"
            )
    return tuple(cases)
