"""The Advisor gate's code checks and the judge call, through ``review_suggestion``.

Seam: the public ``review_suggestion`` with a scripted judge. No database or Redis.
"""

from __future__ import annotations

from collections.abc import Sequence

from metis.agent.gate import GateContext, GateDecisionKind
from metis.agent.tools.advice_gate import (
    AdviceBrief,
    WeakParam,
    build_advice_gate,
    review_suggestion,
)
from metis.agent.tools.scoring import SourceBook
from metis.modules.scoring import NewEvidence, NewSuggestion, ScoreParam, SuggestionKind

KNOWN = "https://example.com/report"
WEAK = (
    WeakParam(ScoreParam.UNIQUENESS, 3, "Many rivals do the same."),
    WeakParam(ScoreParam.MARKET_DEMAND, 4, "No sign of demand."),
)
BRIEF = AdviceBrief("Invoice chase", "Reminders for late invoices.", WEAK)


class ScriptedJudge:
    def __init__(self, *verdicts: str | None) -> None:
        self.verdicts = list(verdicts)
        self.items: list[str] = []

    async def verdict(self, instruction: str, item: str) -> str | None:
        self.items.append(item)
        return self.verdicts.pop(0) if self.verdicts else None


def suggestion(
    title: str = "Niche down to agencies",
    params: Sequence[ScoreParam] = (ScoreParam.UNIQUENESS,),
    url: str = KNOWN,
) -> NewSuggestion:
    return NewSuggestion(
        kind=SuggestionKind.NICHE,
        title=title,
        rationale="Agencies chase many invoices a week.",
        target_params=tuple(params),
        expected_impact="uniqueness up by about 2 marks",
        evidence=(NewEvidence(url=url, title="Report", quote="Agencies chase many invoices."),),
    )


async def review(
    candidate: NewSuggestion,
    judge: ScriptedJudge,
    saved: Sequence[str] = (),
) -> GateDecisionKind:
    context = GateContext(judge=judge, budget=None, emit=lambda event: None)
    book = SourceBook()
    book.add([KNOWN])
    decision = await review_suggestion(context, build_advice_gate(book), BRIEF, saved, candidate)
    return decision.kind


async def test_a_specific_sourced_suggestion_on_a_weak_parameter_passes() -> None:
    judge = ScriptedJudge(None)

    assert await review(suggestion(), judge) is GateDecisionKind.PASSED
    assert len(judge.items) == 1


async def test_the_judge_reads_the_suggestion_the_idea_and_the_weak_parameters() -> None:
    judge = ScriptedJudge(None)

    await review(suggestion(), judge, saved=["Charge per seat"])

    item = judge.items[0]
    assert "Niche down to agencies" in item and "Reminders for late invoices." in item
    assert "Many rivals do the same." in item and "Charge per seat" in item


async def test_a_judge_rejection_is_a_retry_with_its_reason() -> None:
    judge = ScriptedJudge("Too generic.")

    assert await review(suggestion(), judge) is GateDecisionKind.RETRIED


async def test_a_suggestion_on_no_weak_parameter_is_rejected_without_the_judge() -> None:
    judge = ScriptedJudge(None)

    assert await review(suggestion(params=[ScoreParam.TIMING]), judge) is GateDecisionKind.RETRIED
    assert judge.items == []


async def test_one_weak_parameter_among_others_is_enough() -> None:
    judge = ScriptedJudge(None)
    candidate = suggestion(params=[ScoreParam.TIMING, ScoreParam.MARKET_DEMAND])

    assert await review(candidate, judge) is GateDecisionKind.PASSED


async def test_a_source_the_run_never_saw_is_rejected_without_the_judge() -> None:
    judge = ScriptedJudge(None)

    assert await review(suggestion(url="https://invented.example.com/x"), judge) is (
        GateDecisionKind.RETRIED
    )
    assert judge.items == []


async def test_a_known_source_with_a_fragment_or_trailing_slash_passes() -> None:
    judge = ScriptedJudge(None)

    assert await review(suggestion(url=KNOWN + "/#top"), judge) is GateDecisionKind.PASSED


async def test_a_near_duplicate_title_is_rejected_whatever_the_word_order_or_case() -> None:
    judge = ScriptedJudge(None)

    assert await review(
        suggestion("agencies, Niche down to"), judge, saved=["Niche down to agencies"]
    ) is (GateDecisionKind.RETRIED)
    assert judge.items == []


async def test_a_different_title_is_not_a_duplicate() -> None:
    judge = ScriptedJudge(None)

    assert await review(suggestion("Charge per seat"), judge, saved=["Niche down to agencies"]) is (
        GateDecisionKind.PASSED
    )


async def test_an_unreadable_judge_reply_lets_the_suggestion_through() -> None:
    class Broken:
        async def verdict(self, instruction: str, item: str) -> str | None:
            raise ValueError("unreadable judge reply")

    context = GateContext(judge=Broken(), budget=None, emit=lambda event: None)
    book = SourceBook()
    book.add([KNOWN])

    decision = await review_suggestion(context, build_advice_gate(book), BRIEF, (), suggestion())

    assert decision.kind is GateDecisionKind.PASSED


async def test_the_third_rejection_skips_and_a_settled_suggestion_resets_the_count() -> None:
    judge = ScriptedJudge("No.", "No.", "No.", "No.")
    context = GateContext(judge=judge, budget=None, emit=lambda event: None)
    book = SourceBook()
    book.add([KNOWN])
    gate = build_advice_gate(book)

    kinds = [
        (await review_suggestion(context, gate, BRIEF, (), suggestion(f"Vague {n}"))).kind
        for n in range(4)
    ]

    assert kinds == [
        GateDecisionKind.RETRIED,
        GateDecisionKind.RETRIED,
        GateDecisionKind.SKIPPED,
        GateDecisionKind.RETRIED,  # the next suggestion starts with a fresh count
    ]
