"""The Advisor's own tools: save a suggestion, finish the advice.

``save_suggestion`` refuses a suggestion past the allowed count. Every other check is the
``advice_output`` gate (``advice_gate.py``): a suggestion that targets none of the weakest
parameters, repeats a saved one, cites a URL the run never saw, or is generic or unsupported is
refused with the reason; after two retries it is skipped. A refusal is a message the model can
act on; a skip tells the model to go on without it. Neither fails the run. ``finish_advice`` is
the Advisor's structured end: for a score below 55 it is refused while fewer than the minimum
are saved. The first such refusal lets the model go on; the second closes it, and the node then
fails the run rather than leave thin advice (unless gate skips caused the shortfall).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool
from redis.asyncio import Redis

from metis.agent.gate import Gate, GateContext, GateDecisionKind, GateRefusal
from metis.agent.tools.advice_gate import AdviceBrief, review_suggestion
from metis.agent.tools.research_kb import ResearchScope
from metis.agent.tools.scoring import NoArgs
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
SKIPPED = "Suggestion skipped: it did not pass review and was not saved."
SKIP_COUNTER_TTL_SECONDS = 24 * 3600
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
    skipped: int = 0


class SkipCounter:
    """Suggestions the gate skipped for one score, kept in Redis so a re-run still knows.

    A below-55 score may end short only because of skips; the node re-runs after the user's
    decision and must then see that the shortfall is settled, not advise again.
    """

    def __init__(self, redis: Redis, run_id: UUID, score_run_id: UUID) -> None:
        self._redis = redis
        self._key = f"agent:advice:{run_id}:{score_run_id}:skipped"

    async def record(self) -> None:
        try:
            await self._redis.incr(self._key)
            await self._redis.expire(self._key, SKIP_COUNTER_TTL_SECONDS)
        except Exception:  # noqa: BLE001  (a lost counter must not fail the suggestion)
            logger.warning("advice.skip_counter_failed")

    async def count(self) -> int:
        try:
            return int(await self._redis.get(self._key) or 0)
        except Exception:  # noqa: BLE001
            logger.warning("advice.skip_counter_failed")
            return 0


@dataclass(frozen=True)
class AdviceReview:
    """What ``save_suggestion`` needs to review a suggestion: the gate, its context and the idea."""

    gate: Gate
    context: GateContext
    brief: AdviceBrief
    skips: SkipCounter


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
    scope: ResearchScope, plan: AdvicePlan, review: AdviceReview, ledger: AdviceLedger
) -> list[BaseTool]:
    """The Advisor's own tools (the KB lookup and the Exa search are added by the node)."""
    return [_save_suggestion(scope, plan, review, ledger), _finish_advice(plan, ledger)]


def _save_suggestion(
    scope: ResearchScope, plan: AdvicePlan, review: AdviceReview, ledger: AdviceLedger
) -> BaseTool:
    async def save_suggestion(
        kind: SuggestionKind,
        title: str,
        rationale: str,
        target_params: tuple[ScoreParam, ...],
        expected_impact: str,
        evidence: tuple[NewEvidence, ...],
    ) -> str:
        if len(ledger.saved) >= plan.maximum:
            raise AdviceRefused(
                f"Nothing was saved. The limit of {plan.maximum} suggestions is reached. "
                f"Call {FINISH_ADVICE}."
            )
        data = NewSuggestion(
            kind=kind,
            title=title,
            rationale=rationale,
            target_params=target_params,
            expected_impact=expected_impact,
            evidence=evidence,
        )
        decision = await review_suggestion(
            review.context, review.gate, review.brief, await _saved_titles(scope, plan), data
        )
        if decision.kind is GateDecisionKind.RETRIED:
            raise GateRefusal("Nothing was saved. " + decision.reason)
        if decision.kind is GateDecisionKind.SKIPPED:
            ledger.skipped += 1
            await review.skips.record()
            return (
                f"{SKIPPED} ({decision.reason}) Suggest something different, or call "
                f"{FINISH_ADVICE}."
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


async def _saved_titles(scope: ResearchScope, plan: AdvicePlan) -> list[str]:
    """Titles of every suggestion saved for this score, earlier passes included."""
    async with scope.session() as session:
        listed = await scoring.list_suggestions(
            session, scope.workspace_id, scope.idea_id, plan.score.id
        )
    return [suggestion.title for suggestion in listed.items]
