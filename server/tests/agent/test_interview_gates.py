"""The Interviewer's gates without a run: the review of one candidate question.

Seam: ``review_question`` with a fake judge, as ``test_gate.py`` does for the framework. The
job-level behaviour (turns, events, run status) is in ``test_interviewer_gates.py``.
"""

from __future__ import annotations

import pytest

from metis.agent.gate import GateContext
from metis.agent.tools.interview_gates import (
    OUTPUT_INSTRUCTION,
    IdeaTexts,
    ReviewOutcome,
    review_question,
    verified_quote,
)
from metis.agent.tools.question_options import OptionArgs
from tests.agent.test_gate import FakeJudge, Recorder

IDEA = IdeaTexts(
    title="Invoice chase",
    text="Polite, escalating payment reminders for freelancers with late invoices.",
    turns=[("Who pays?", "The freelancer, about $12 a month.")],
)
GOOD = "Which of your reminders would a late-paying client dread the most?"
OPTIONS = [OptionArgs(label="Email"), OptionArgs(label="Text message")]


class OutputRejecter(FakeJudge):
    """Passes every input review and rejects every output review with ``reason``."""

    def __init__(self, reason: str) -> None:
        super().__init__(None)
        self._reason = reason

    async def verdict(self, instruction: str, item: str) -> str | None:
        self.calls += 1
        return self._reason if instruction == OUTPUT_INSTRUCTION else None


def _context(judge: FakeJudge | None) -> tuple[GateContext, Recorder]:
    recorder = Recorder()
    return GateContext(judge=judge, budget=None, emit=recorder), recorder


async def test_a_worthy_question_is_asked() -> None:
    context, _ = _context(FakeJudge(None))

    review = await review_question(context, IDEA, GOOD)

    assert review.outcome is ReviewOutcome.ASK


async def test_a_question_that_repeats_an_earlier_one_is_revised_without_the_judge() -> None:
    judge = FakeJudge(None)
    context, _ = _context(judge)

    review = await review_question(context, IDEA, "Who pays")

    assert review.outcome is ReviewOutcome.REVISE
    assert "repeats an earlier question" in review.text
    assert judge.calls == 0


async def test_a_generic_question_is_rejected_by_the_output_gate() -> None:
    context, events = _context(FakeJudge(None, "Could be asked of any idea."))

    review = await review_question(context, IDEA, "What is the pain?")

    assert review.outcome is ReviewOutcome.REVISE
    assert review.text == "Could be asked of any idea."
    assert [e["gate"] for e in events.events] == ["interview_input", "interview_output"]


async def test_an_answer_quoted_from_the_idea_ends_the_question_at_once() -> None:
    context, _ = _context(FakeJudge('answered: "payment reminders for freelancers"'))

    review = await review_question(context, IDEA, "Who is this for?")

    assert (review.outcome, review.text) == (
        ReviewOutcome.ANSWERED,
        "payment reminders for freelancers",
    )


async def test_an_answer_quoted_from_an_earlier_answer_counts() -> None:
    context, _ = _context(FakeJudge('answered: "about $12 a month"'))

    review = await review_question(context, IDEA, "What would they pay?")

    assert review.outcome is ReviewOutcome.ANSWERED


async def test_the_third_rejection_skips_the_question() -> None:
    context, _ = _context(OutputRejecter("Too generic."))
    outcomes: list[ReviewOutcome] = []

    for _ in range(3):
        outcomes.append((await review_question(context, IDEA, "What is the pain?")).outcome)

    assert outcomes == [ReviewOutcome.REVISE, ReviewOutcome.REVISE, ReviewOutcome.SKIP]


async def test_bad_options_are_rejected_by_the_output_gate_without_a_judge_call() -> None:
    judge = FakeJudge(None)
    context, _ = _context(judge)

    review = await review_question(context, IDEA, GOOD, [OptionArgs(label="Only one")])

    assert review.outcome is ReviewOutcome.REVISE
    assert "Give 2 to 5 options" in review.text
    assert judge.calls == 1  # the input gate's judge only


async def test_valid_options_pass() -> None:
    context, _ = _context(FakeJudge(None))

    review = await review_question(context, IDEA, GOOD, OPTIONS)

    assert review.outcome is ReviewOutcome.ASK


async def test_a_judge_error_lets_the_question_through() -> None:
    context, _ = _context(FakeJudge(RuntimeError("boom")))

    review = await review_question(context, IDEA, GOOD)

    assert review.outcome is ReviewOutcome.ASK


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ('answered: "PAYMENT REMINDERS   for freelancers"', "PAYMENT REMINDERS   for freelancers"),
        ("answered: “about $12 a month”", "about $12 a month"),
        ('answered: "sold to dentists"', None),
        ('answered: ""', None),
        ("Could be asked of any idea.", None),
    ],
)
def test_a_quote_counts_only_when_it_is_in_the_idea_or_an_answer(
    reason: str, expected: str | None
) -> None:
    assert verified_quote(reason, IDEA) == expected


async def test_rewording_a_rejected_question_does_not_restart_the_retry_count() -> None:
    context, _ = _context(OutputRejecter("Too generic."))
    wordings = ["What is the pain?", "What hurts most?", "Where is the problem?"]
    outcomes = [(await review_question(context, IDEA, w)).outcome for w in wordings]

    assert outcomes == [ReviewOutcome.REVISE, ReviewOutcome.REVISE, ReviewOutcome.SKIP]


async def test_a_settled_question_leaves_the_next_one_a_fresh_retry_count() -> None:
    context, _ = _context(OutputRejecter("Too generic."))
    for wording in ("What is the pain?", "What hurts most?", "Where is the problem?"):
        await review_question(context, IDEA, wording)  # the third is skipped

    review = await review_question(context, IDEA, "Is there a market?")

    assert review.outcome is ReviewOutcome.REVISE


async def test_the_output_gate_judge_sees_the_idea_options_and_question() -> None:
    seen: list[str] = []

    class Spy(FakeJudge):
        async def verdict(self, instruction: str, item: str) -> str | None:
            seen.append(item)
            return await super().verdict(instruction, item)

    context, _ = _context(Spy(None))
    await review_question(context, IDEA, GOOD, OPTIONS)

    assert all(IDEA.title in item and GOOD in item for item in seen)
    assert "Text message" in seen[-1]
