"""Gate eval cases: one JSON object per line of ``gates/cases.jsonl``, validated on load.

A case freezes a candidate interview question with everything the gates read (the idea's title
and text, the earlier turns) and the verdict it must get: ``ask`` (a good question passes),
``revise`` (a generic question or a near-duplicate is rejected) or ``answered`` (the answer is
already in the idea or an earlier answer, so the question is skipped and saved as a turn).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

CASES_PATH = Path(__file__).parent / "gates" / "cases.jsonl"
RECORDED_PATH = Path(__file__).parent / "gates" / "recorded.jsonl"
RESEARCH_CASES_PATH = Path(__file__).parent / "gates" / "research_cases.jsonl"
RESEARCH_RECORDED_PATH = Path(__file__).parent / "gates" / "research_recorded.jsonl"

CaseId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=60)]
Expect = Literal["ask", "revise", "answered"]
ResearchExpect = Literal["run", "refuse"]
ResearchTool = Literal["web_search_exa", "web_fetch_exa"]


class GateCaseFileError(ValueError):
    """A case file that cannot be used; the message names the line."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GateIdea(_Frozen):
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)


class GateTurn(_Frozen):
    question: str = Field(min_length=1)
    answer: str | None = None


class GateOption(_Frozen):
    label: str
    detail: str | None = None
    recommended: bool = False


class GateCase(_Frozen):
    id: CaseId
    idea: GateIdea
    turns: tuple[GateTurn, ...] = ()
    question: str = Field(min_length=1)
    options: tuple[GateOption, ...] = ()
    expect: Expect


def load_gate_cases(path: Path = CASES_PATH) -> tuple[GateCase, ...]:
    """The cases of ``path``; raises ``GateCaseFileError`` on a bad line or a repeated id."""
    cases: list[GateCase] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(GateCase.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise GateCaseFileError(f"{path.name} line {number}: {exc}") from exc
    ids = [case.id for case in cases]
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise GateCaseFileError(f"{path.name}: repeated case id(s): {', '.join(repeated)}")
    if not cases:
        raise GateCaseFileError(f"{path.name}: no cases")
    return tuple(cases)


class KbMatchCase(_Frozen):
    name: str
    url: str
    description: str | None = None
    pricing: str | None = None


class ResearchGateCase(_Frozen):
    """A candidate Exa call with everything the Researcher's gate reads, and its verdict.

    ``run``: the call passes. ``refuse``: it is rejected, by a code check (a repeated search or
    page) or by the judge (vague, no gap, answered by the KB). ``target`` is the query of a
    search or the URL of a fetch.
    """

    id: CaseId
    idea: GateIdea
    brief: str = "{}"
    saved: tuple[str, ...] = ()
    saved_urls: tuple[str, ...] = ()
    earlier_queries: tuple[str, ...] = ()
    fetched_urls: tuple[str, ...] = ()
    kb_matches: tuple[KbMatchCase, ...] = ()
    tool: ResearchTool
    target: str = Field(min_length=1)
    expect: ResearchExpect


def load_research_gate_cases(path: Path = RESEARCH_CASES_PATH) -> tuple[ResearchGateCase, ...]:
    """The Researcher cases of ``path``; raises ``GateCaseFileError`` on a bad line or repeat."""
    cases: list[ResearchGateCase] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(ResearchGateCase.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise GateCaseFileError(f"{path.name} line {number}: {exc}") from exc
    ids = [case.id for case in cases]
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise GateCaseFileError(f"{path.name}: repeated case id(s): {', '.join(repeated)}")
    calls = [(c.idea.title, c.tool, c.target) for c in cases]
    if len(set(calls)) != len(calls):
        raise GateCaseFileError(f"{path.name}: two cases share an idea, a tool and a target")
    if not cases:
        raise GateCaseFileError(f"{path.name}: no cases")
    return tuple(cases)
