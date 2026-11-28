"""The Advisor's output gate and the review of one candidate suggestion.

``advice_output`` decides whether a suggestion is worth saving. Code checks run first and never
fail open: it targets one of the weakest parameters, it differs from the suggestions already
saved for this score, and every source URL was seen by the run. Then the judge decides whether
it would move the score, is specific to this idea (not generic, not what the idea already does),
and is supported by its quotes, in the soul's tone. The gate is a ``Gate`` over the shared
framework in ``metis.agent.gate``; no retry logic lives here.

``review_suggestion`` serves both the ``save_suggestion`` tool and the gate evals. Retries are
counted per suggestion slot across rewordings and reset once a suggestion is settled.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from metis.agent.gate import Gate, GateContext, GateDecision, GateDecisionKind, run_gate
from metis.agent.text_match import is_near_duplicate
from metis.agent.tools.scoring import SourceBook
from metis.modules.scoring import NewSuggestion, ScoreParam

SPECIALIST = "advisor"
GATE_NAME = "advice_output"
# One slot: a reworded suggestion is still the same attempt, so a model that keeps revising a
# weak suggestion is skipped after ``MAX_RETRIES``.
ATTEMPT_KEY = "suggestion"

JUDGE_INSTRUCTION = """\
The item is a candidate suggestion for improving an idea, with the idea, its weakest score
parameters (with the score's reason for each) and the titles of the suggestions already saved.
Reject the suggestion when any of these is true:
1. It would not move the score: it does not plausibly raise a parameter it targets, or the
   expected impact does not follow from it.
2. It is generic: it could be given to any idea unchanged (for example "improve marketing" or
   "add more features"), or it only restates what the idea already does.
3. A source's quote does not support the claim it is cited for, or the quote says something else.
4. Its tone breaks the voice of Metis: flattery, hype, emoji, or a verdict on the idea.
Otherwise pass it."""


@dataclass(frozen=True)
class WeakParam:
    """One of the weakest parameters of the score: its mark and the score's reason for it."""

    param: ScoreParam
    raw: int
    reason: str


@dataclass(frozen=True)
class AdviceBrief:
    """What the judge reads about the idea: its words and the parameters that hold it back."""

    idea_title: str
    idea_text: str
    weakest: tuple[WeakParam, ...]


def build_advice_gate(book: SourceBook) -> Gate:
    """The gate for one run; ``book`` holds the URLs the run saw (the research, score, searches)."""
    return Gate(
        name=GATE_NAME,
        specialist=SPECIALIST,
        checks=(_targets_a_weak_parameter, _differs_from_saved, _sources_were_seen(book)),
        judge_instruction=JUDGE_INSTRUCTION,
    )


async def review_suggestion(
    context: GateContext,
    gate: Gate,
    brief: AdviceBrief,
    saved_titles: Sequence[str],
    suggestion: NewSuggestion,
) -> GateDecision:
    """Run the gate on one candidate suggestion.

    ``RETRIED`` means the model may revise it; ``SKIPPED`` means drop it. Either way the reason
    is in the decision. A passed or skipped suggestion starts the next one with a fresh count.
    """
    decision = await run_gate(gate, ATTEMPT_KEY, _item(brief, saved_titles, suggestion), context)
    if decision.kind is not GateDecisionKind.RETRIED:
        context.attempts.pop((gate.name, ATTEMPT_KEY), None)
    return decision


def _item(
    brief: AdviceBrief, saved_titles: Sequence[str], suggestion: NewSuggestion
) -> dict[str, Any]:
    return {
        "suggestion": suggestion.model_dump(mode="json"),
        "idea_title": brief.idea_title,
        "idea_text": brief.idea_text,
        "weakest": [
            {"param": weak.param.value, "raw": weak.raw, "reason": weak.reason}
            for weak in brief.weakest
        ],
        "saved_titles": list(saved_titles),
    }


def _targets_a_weak_parameter(item: Any) -> str | None:
    weakest = [weak["param"] for weak in item["weakest"]]
    if set(item["suggestion"]["target_params"]) & set(weakest):
        return None
    return f"Target at least one of the weakest parameters: {', '.join(weakest)}."


def _differs_from_saved(item: Any) -> str | None:
    title = item["suggestion"]["title"]
    for saved in item["saved_titles"]:
        if is_near_duplicate(title, saved):
            return (
                f'This repeats a suggestion already saved: "{saved}". Suggest something different.'
            )
    return None


def _sources_were_seen(book: SourceBook) -> Any:
    def check(item: Any) -> str | None:
        unknown = [e["url"] for e in item["suggestion"]["evidence"] if not book.knows(e["url"])]
        if not unknown:
            return None
        return (
            f"Evidence {', '.join(unknown)} is not a source from the research, the score or "
            "your searches."
        )

    return check
