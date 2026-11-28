"""The Interviewer's two gates and the review of one candidate question.

``interview_input`` decides whether a question is worth asking at all (would a different answer
change the research, the score or the spec? is the answer already in the idea text or an earlier
answer? is it a near-duplicate?). ``interview_output`` checks the question itself (not generic,
in the soul's tone, with valid options). Both are ``Gate`` values over the shared framework in
``metis.agent.gate``; no retry logic lives here.

``review_question`` runs the input gate, then the output gate, and says what to do with the
question: ask it, revise it, drop it, or record the answer that is already known. It never raises
and never fails a run, so the same function serves the ``ask_user`` tool and the gate evals.

The judge marks an already-answered question with ``answered: "<exact quote>"``. The quote is only
believed when it appears in the idea text or an earlier answer (checked here, in code).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from metis.agent.gate import Gate, GateContext, GateDecisionKind, run_gate
from metis.agent.text_match import is_near_duplicate, normalised
from metis.agent.tools.question_options import OptionArgs, check_options

SPECIALIST = "interviewer"
INPUT_GATE_NAME = "interview_input"
OUTPUT_GATE_NAME = "interview_output"
# Retries are counted per question slot, not per wording: a reworded question is still the
# same attempt to ask, so a model that keeps revising is skipped after ``MAX_RETRIES``.
ATTEMPT_KEY = "question"
MAX_QUOTE_LENGTH = 2_000
ANSWERED_MARKER = "answered:"
_QUOTE = re.compile(r"""answered:\s*["“](?P<quote>.+?)["”]\s*$""", re.IGNORECASE)

INPUT_INSTRUCTION = f"""\
The item is a candidate interview question with the idea and the earlier questions and answers.
Reject the question when any of these is true:
1. No plausible answer would change the research, the score or the spec of this idea.
2. The idea text or an earlier answer already answers it. Reply
   `REJECT: {ANSWERED_MARKER} "<the exact words from the idea text or the earlier answer>"`
   and copy the quote word for word.
3. It asks the same thing as an earlier question, even in different words.
Otherwise pass it."""

OUTPUT_INSTRUCTION = """\
The item is a candidate interview question, its options and the idea it is about.
Reject the question when any of these is true:
1. It could be asked of any idea unchanged, for example "What is the pain?" or "Who is your
   customer?". A good question names something specific to this idea, in the idea's own words.
2. Its tone breaks the voice of Metis: flattery, hype, emoji, a verdict, or a leading question.
3. Its options are not distinct likely answers, or a recommended option is not supported by the
   idea text or an earlier answer.
Otherwise pass it."""


class ReviewOutcome(StrEnum):
    ASK = "ask"
    REVISE = "revise"
    SKIP = "skip"
    ANSWERED = "answered"


@dataclass(frozen=True)
class QuestionReview:
    """What to do with a candidate question. ``text`` is the reason, or the quoted answer."""

    outcome: ReviewOutcome
    text: str = ""


@dataclass(frozen=True)
class IdeaTexts:
    """What the gates read about the idea: its words and the earlier questions and answers."""

    title: str
    text: str
    turns: Sequence[tuple[str, str | None]]


def _near_duplicate(item: Any) -> str | None:
    question = item["question"]
    for turn in item["earlier_turns"]:
        earlier = turn["question"]
        if is_near_duplicate(question, earlier):
            return f'This repeats an earlier question: "{earlier}". Ask about something new.'
    return None


def _valid_options(item: Any) -> str | None:
    if not item["options"]:
        return None
    options = [OptionArgs.model_validate(option) for option in item["options"]]
    return check_options(options, multi=item["multi"])


INPUT_GATE = Gate(
    name=INPUT_GATE_NAME,
    specialist=SPECIALIST,
    checks=(_near_duplicate,),
    judge_instruction=INPUT_INSTRUCTION,
)
OUTPUT_GATE = Gate(
    name=OUTPUT_GATE_NAME,
    specialist=SPECIALIST,
    checks=(_valid_options,),
    judge_instruction=OUTPUT_INSTRUCTION,
)


def verified_quote(reason: str, idea: IdeaTexts) -> str | None:
    """The quote in an ``answered`` reason, if it appears in the idea text or an earlier answer."""
    match = _QUOTE.search(reason.strip())
    if match is None:
        return None
    quote = match["quote"].strip()
    needle = normalised(quote)
    if not needle:
        return None
    sources = [idea.text, *(answer for _, answer in idea.turns if answer)]
    if any(needle in normalised(source) for source in sources):
        return quote[:MAX_QUOTE_LENGTH]
    return None


async def review_question(
    context: GateContext,
    idea: IdeaTexts,
    question: str,
    options: Sequence[OptionArgs] = (),
    *,
    multi: bool = False,
) -> QuestionReview:
    """Run the input gate, then the output gate, on one candidate question.

    A rejection is ``REVISE`` while the framework still allows a retry and ``SKIP`` after that;
    a rejection that quotes a verified answer is ``ANSWERED`` at once, since the question must
    not be asked in any wording. Retries are counted across rewordings (see ``ATTEMPT_KEY``).
    """
    review = await _review(context, idea, question, options, multi)
    if review.outcome is not ReviewOutcome.REVISE:
        _forget_attempts(context)
    return review


async def _review(
    context: GateContext,
    idea: IdeaTexts,
    question: str,
    options: Sequence[OptionArgs],
    multi: bool,
) -> QuestionReview:
    first = await run_gate(INPUT_GATE, ATTEMPT_KEY, _input_item(idea, question), context)
    if first.kind is not GateDecisionKind.PASSED:
        if (quote := verified_quote(first.reason, idea)) is not None:
            return QuestionReview(ReviewOutcome.ANSWERED, quote)
        return _rejected(first.kind, first.reason)
    item = _output_item(idea, question, options, multi)
    second = await run_gate(OUTPUT_GATE, ATTEMPT_KEY, item, context)
    if second.kind is not GateDecisionKind.PASSED:
        return _rejected(second.kind, second.reason)
    return QuestionReview(ReviewOutcome.ASK)


def _forget_attempts(context: GateContext) -> None:
    """Start the next question with a fresh retry count (the question is settled)."""
    for gate_name in (INPUT_GATE_NAME, OUTPUT_GATE_NAME):
        context.attempts.pop((gate_name, ATTEMPT_KEY), None)


def _rejected(kind: GateDecisionKind, reason: str) -> QuestionReview:
    outcome = ReviewOutcome.REVISE if kind is GateDecisionKind.RETRIED else ReviewOutcome.SKIP
    return QuestionReview(outcome, reason)


def _input_item(idea: IdeaTexts, question: str) -> dict[str, Any]:
    return {
        "question": question,
        "idea_title": idea.title,
        "idea_text": idea.text,
        "earlier_turns": [{"question": q, "answer": a} for q, a in idea.turns],
    }


def _output_item(
    idea: IdeaTexts, question: str, options: Sequence[OptionArgs], multi: bool
) -> dict[str, Any]:
    return {
        **_input_item(idea, question),
        "options": [option.model_dump() for option in options],
        "multi": multi,
    }
