"""The Advisor's own tools: save a suggestion, finish the advice.

``save_suggestion`` refuses a suggestion past the allowed count, one that targets none of the
weakest parameters, or one whose evidence points at a URL the run never saw (the research,
the score's own evidence, or the Advisor's searches). A refusal is a message the model can act
on; it never fails the run. ``finish_advice`` is the Advisor's structured end: for a score below
55 it is refused while fewer than the minimum are saved. The first such refusal lets the model
go on; the second closes it, and the node then fails the run rather than leave thin advice.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool

from metis.agent.tools.research_kb import ResearchScope
from metis.agent.tools.scoring import NoArgs, SourceBook
from metis.core.logging import get_logger
from metis.modules import scoring
from metis.modules.scoring import (
    NewEvidence,
    NewSuggestion,
    ScoreBand,
    ScoreParam,
    ScoreRun,
    SuggestionKind,
)

SAVE_SUGGESTION = "save_suggestion"
FINISH_ADVICE = "finish_advice"
MAX_REFUSALS = 2
MAX_RAW = 10
ADVISE_MIN = 3
ADVISE_MAX = 5
PROMISING_MAX = 2
ADVISE_TARGETS = 3
PROMISING_TARGETS = 2
CLOSED = "Finishing is closed: two attempts were refused. Stop."
SAVED = "Suggestion saved."
FINISHED = "Advice finished."

logger = get_logger(__name__)


class AdviceRefused(Exception):
    """A call the model must fix; its text is what the model reads."""

    def __repr__(self) -> str:
        return str(self)


@dataclass(frozen=True)
class AdvicePlan:
    """What the Advisor owes for one score: how many suggestions, aimed at which parameters."""

    score: ScoreRun
    minimum: int
    maximum: int
    targets: tuple[ScoreParam, ...]


# Run-scoped accumulator that the tool closures fill while the loop runs and the node reads.
@dataclass
class AdviceLedger:
    """The suggestions saved for the score so far (earlier passes included) and the refusals."""

    saved: list[UUID] = field(default_factory=list)
    refusals: int = 0


def plan_for(score: ScoreRun) -> AdvicePlan | None:
    """The plan for ``score``, or ``None`` when it needs no advice (the ``build`` band)."""
    if score.band is ScoreBand.ADVISE:
        return AdvicePlan(score, ADVISE_MIN, ADVISE_MAX, weakest_params(score, ADVISE_TARGETS))
    if score.band is ScoreBand.PROMISING:
        return AdvicePlan(score, 0, PROMISING_MAX, weakest_params(score, PROMISING_TARGETS))
    return None


def weakest_params(score: ScoreRun, count: int) -> tuple[ScoreParam, ...]:
    """The ``count`` parameters that lost the most points (``weight × (10 − raw)``).

    Ties go to the heavier weight, then to rubric order.
    """
    ranked = sorted(
        score.params,
        key=lambda p: (-(p.weight * (MAX_RAW - p.raw)), -p.weight, list(ScoreParam).index(p.param)),
    )
    return tuple(p.param for p in ranked[:count])


def advice_tools(
    scope: ResearchScope, plan: AdvicePlan, book: SourceBook, ledger: AdviceLedger
) -> list[BaseTool]:
    """The Advisor's own tools (the KB lookup and the Exa search are added by the node)."""
    return [_save_suggestion(scope, plan, book, ledger), _finish_advice(plan, ledger)]


def _save_suggestion(
    scope: ResearchScope, plan: AdvicePlan, book: SourceBook, ledger: AdviceLedger
) -> BaseTool:
    async def save_suggestion(
        kind: SuggestionKind,
        title: str,
        rationale: str,
        target_params: tuple[ScoreParam, ...],
        expected_impact: str,
        evidence: tuple[NewEvidence, ...],
    ) -> str:
        problem = _problem(plan, book, ledger, target_params, evidence)
        if problem is not None:
            raise AdviceRefused("Nothing was saved. " + problem)
        data = NewSuggestion(
            kind=kind,
            title=title,
            rationale=rationale,
            target_params=target_params,
            expected_impact=expected_impact,
            evidence=evidence,
        )
        async with scope.session() as session:
            saved = await scoring.save_suggestion(
                session, scope.workspace_id, scope.idea_id, plan.score.id, data
            )
        ledger.saved.append(saved.id)
        return f"{SAVED} {len(ledger.saved)} of at most {plan.maximum}."

    return StructuredTool.from_function(
        coroutine=save_suggestion,
        name=SAVE_SUGGESTION,
        description=(
            "Save one suggestion that would improve the idea: a kind (feature, niche, pricing "
            "or pivot), a title, the reason, the parameters it targets, the expected impact "
            "and at least one source from the research or your own searches."
        ),
        args_schema=NewSuggestion,
    )


def _finish_advice(plan: AdvicePlan, ledger: AdviceLedger) -> BaseTool:
    async def finish_advice() -> str:
        if ledger.refusals >= MAX_REFUSALS:
            return CLOSED
        missing = plan.minimum - len(ledger.saved)
        if missing <= 0:
            return FINISHED
        ledger.refusals += 1
        logger.warning("advice.finish_refused", refusals=ledger.refusals, missing=missing)
        if ledger.refusals >= MAX_REFUSALS:
            return CLOSED
        raise AdviceRefused(
            f"Too few suggestions: save {missing} more (at least {plan.minimum}), then finish."
        )

    return StructuredTool.from_function(
        coroutine=finish_advice,
        name=FINISH_ADVICE,
        description="Finish the advice once the suggestions are saved.",
        args_schema=NoArgs,
    )


def _problem(
    plan: AdvicePlan,
    book: SourceBook,
    ledger: AdviceLedger,
    target_params: Sequence[ScoreParam],
    evidence: Sequence[NewEvidence],
) -> str | None:
    if len(ledger.saved) >= plan.maximum:
        return f"The limit of {plan.maximum} suggestions is reached. Call {FINISH_ADVICE}."
    if not set(target_params) & set(plan.targets):
        weakest = ", ".join(p.value for p in plan.targets)
        return f"Target at least one of the weakest parameters: {weakest}."
    unknown = [item.url for item in evidence if not book.knows(item.url)]
    if unknown:
        return (
            f"Evidence {', '.join(unknown)} is not a source from the research, the score or "
            "your searches."
        )
    return None
