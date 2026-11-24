"""The Scorer's own tools: read the rubric, look up the KB, submit the six marks.

``submit_scores`` is the Scorer's structured output. It refuses a submission whose evidence
points at a URL the run never saw (the research snapshot or the Scorer's own searches), and
turns the ``scoring`` module's refusals into messages the model can act on. The first refusal
lets the model try again; the second closes submission, so the node fails the run instead of
storing a score it cannot stand behind. The marks go to ``scoring.record_score``; the total and
band are computed there, never stated by the model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urldefrag

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, ValidationError

from metis.agent.tools.research_kb import ResearchScope
from metis.agent.tools.score_scale import SCALE
from metis.core.errors import MetisError
from metis.core.logging import get_logger
from metis.modules import scoring
from metis.modules.scoring import NewParamScore, ScoreParam, ScoreRun, ScoreTrigger

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

GET_RUBRIC = "get_rubric"
SUBMIT_SCORES = "submit_scores"
MAX_REFUSALS = 2
CLOSED = "Submission is closed: two submissions were refused. Stop."

logger = get_logger(__name__)


class ScoreRefused(Exception):
    """A submission the model must fix; its text is what the model reads."""

    def __repr__(self) -> str:
        return str(self)


class NoArgs(BaseModel):
    """A tool that takes no arguments."""


class SubmitScoresArgs(BaseModel):
    """The Scorer's structured output: one entry per parameter, and no total or band."""

    params: tuple[NewParamScore, ...]


class SubmitScoresCall(BaseModel):
    """What the model sends. The entries are checked in the tool, not by the tool node, so a
    malformed entry is a refusal the model can fix (and that counts toward the retry limit)
    instead of an error the loop never counts."""

    params: list[dict[str, Any]] = Field(
        description=(
            "Exactly six entries, one per parameter, each "
            "{param: one of " + ", ".join(p.value for p in ScoreParam) + "; "
            "raw: integer 0-10; reason: text; confidence: 0-1; "
            "evidence: up to 5 of {url, title, quote}; no_evidence: true when evidence is empty}. "
            "The total is computed for you."
        )
    )


# The two classes below are deliberately mutable: run-scoped accumulators that the tool closures
# fill while the loop runs, and the node reads afterwards.
@dataclass
class SourceBook:
    """The URLs this run has seen, compared without a fragment or a trailing slash."""

    _urls: set[str] = field(default_factory=set)

    def add(self, urls: Iterable[str]) -> None:
        self._urls.update(normalize_url(url) for url in urls)

    def knows(self, url: str) -> bool:
        return normalize_url(url) in self._urls


@dataclass
class SubmissionLedger:
    """What the submit tool did in this node run: the stored score and how often it refused."""

    recorded: ScoreRun | None = None
    refusals: int = 0


def normalize_url(url: str) -> str:
    """``url`` trimmed, without its ``#fragment`` and trailing ``/``."""
    return urldefrag(url.strip())[0].rstrip("/")


def collect_search_urls(tools: Sequence[BaseTool], book: SourceBook) -> list[BaseTool]:
    """``tools`` that also add every URL in a search result to ``book``."""

    def collecting(tool: BaseTool) -> BaseTool:
        async def invoke(**arguments: Any) -> Any:
            result = await tool.ainvoke(arguments)
            if isinstance(result, list):
                book.add(
                    row["url"]
                    for row in result
                    if isinstance(row, dict) and isinstance(row.get("url"), str)
                )
            return result

        return StructuredTool.from_function(
            coroutine=invoke,
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
        )

    return [collecting(tool) for tool in tools]


def scoring_tools(
    scope: ResearchScope, book: SourceBook, ledger: SubmissionLedger
) -> list[BaseTool]:
    """The Scorer's own tools (the KB lookup and the Exa search are added by the node)."""
    return [_get_rubric(scope), _submit_scores(scope, book, ledger)]


def _get_rubric(scope: ResearchScope) -> BaseTool:
    async def get_rubric() -> str:
        async with scope.session() as session:
            rubric = await scoring.get_rubric(session)
        return json.dumps(
            {
                "version": rubric.version,
                "marks": "integers 0 to 10; between two anchors is allowed",
                "parameters": [
                    {
                        "param": param.value,
                        "weight": rubric.weights[param],
                        "scale": {str(mark): text for mark, text in SCALE[param].items()},
                    }
                    for param in ScoreParam
                ],
            }
        )

    return StructuredTool.from_function(
        coroutine=get_rubric,
        name=GET_RUBRIC,
        description="The six parameters, their weights and what a mark of 2, 5, 8 and 10 means.",
        args_schema=NoArgs,
    )


def _submit_scores(scope: ResearchScope, book: SourceBook, ledger: SubmissionLedger) -> BaseTool:
    async def submit_scores(params: list[dict[str, Any]]) -> str:
        if ledger.refusals >= MAX_REFUSALS:
            return CLOSED
        entries, problems = _parse(params)
        if not problems:
            problems = _unknown_sources(entries, book)
        if not problems:
            problems = await _record(scope, ledger, entries)
        if not problems:
            return "Scores saved."
        ledger.refusals += 1
        logger.warning("score.submission_refused", refusals=ledger.refusals)
        if ledger.refusals >= MAX_REFUSALS:
            return CLOSED
        raise ScoreRefused("Nothing was saved. Fix this and submit again: " + "; ".join(problems))

    return StructuredTool.from_function(
        coroutine=submit_scores,
        name=SUBMIT_SCORES,
        description=(
            "Submit the marks for all six parameters, each with a reason, evidence and a "
            "confidence. Evidence must come from the research or your own searches."
        ),
        args_schema=SubmitScoresCall,
    )


def _parse(params: list[dict[str, Any]]) -> tuple[tuple[NewParamScore, ...], list[str]]:
    """The entries as ``NewParamScore``, or what is wrong with them."""
    try:
        return SubmitScoresArgs.model_validate({"params": params}).params, []
    except ValidationError as exc:
        return (), [
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
        ]


def _unknown_sources(params: Sequence[NewParamScore], book: SourceBook) -> list[str]:
    return [
        f"{entry.param.value}: evidence {item.url} is not a source from the research or "
        "your searches"
        for entry in params
        for item in entry.evidence
        if not book.knows(item.url)
    ]


async def _record(
    scope: ResearchScope, ledger: SubmissionLedger, params: Sequence[NewParamScore]
) -> list[str]:
    """Store the score; the module's refusals come back as problems."""
    try:
        async with scope.session() as session:
            ledger.recorded = await scoring.record_score(
                session,
                scope.workspace_id,
                scope.idea_id,
                scope.run_id,
                params,
                ScoreTrigger.MANUAL,
            )
    except MetisError as exc:
        if exc.errors is None:
            raise
        return [f"{e['field']}: {e['message']}" for e in exc.errors]
    return []
