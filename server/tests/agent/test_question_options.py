"""Answer options: ids come from the tool, and the proposal rules."""

from __future__ import annotations

import pytest

from metis.agent.tools.question_options import OptionArgs, check_options, question_payload
from metis.modules.ideas import InterviewCoverage, InterviewTopic, question_progress

TOPICS = list(InterviewTopic)[:5]


def _options(count: int) -> list[OptionArgs]:
    return [OptionArgs(label=f"Option {n}") for n in range(count)]


@pytest.mark.parametrize("count", [2, 3, 5])
def test_two_to_five_distinct_options_are_accepted(count: int) -> None:
    assert check_options(_options(count), multi=False) is None


@pytest.mark.parametrize("count", [1, 6])
def test_fewer_than_two_or_more_than_five_options_are_refused(count: int) -> None:
    assert check_options(_options(count), multi=False) is not None


def test_two_recommended_options_need_multi() -> None:
    options = [OptionArgs(label="A", recommended=True), OptionArgs(label="B", recommended=True)]

    assert check_options(options, multi=False) is not None
    assert check_options(options, multi=True) is None


def test_ids_follow_the_position_and_labels_are_trimmed() -> None:
    payload = question_payload(
        "Who?",
        [OptionArgs(label="  A  ", detail="  why  "), OptionArgs(label="B")],
        multi=False,
        allow_free_text=True,
        index=2,
        total=4,
    )

    assert payload["options"] == [
        {"id": "o1", "label": "A", "recommended": False, "detail": "why"},
        {"id": "o2", "label": "B", "recommended": False},
    ]
    assert (payload["index"], payload["total"]) == (2, 4)


def test_a_question_without_options_is_free_text_only() -> None:
    payload = question_payload("Why?", [], multi=True, allow_free_text=False, index=1, total=1)

    assert (payload["options"], payload["multi"], payload["allow_free_text"]) == ([], False, True)


def _coverage(missing: list[InterviewTopic], skipped: list[InterviewTopic], asked: int):
    return InterviewCoverage(
        covered=tuple(t for t in TOPICS if t not in missing),
        missing=tuple(missing),
        skipped=tuple(skipped),
        questions_asked=asked,
        user_ended=False,
    )


def test_total_counts_the_topics_still_to_ask_about() -> None:
    coverage = _coverage(TOPICS, [], asked=1)

    assert question_progress(coverage, InterviewTopic.PROBLEM) == (1, 5)


def test_total_leaves_out_skipped_topics_and_never_drops_below_the_index() -> None:
    coverage = _coverage(
        [InterviewTopic.PAYMENT, InterviewTopic.FEASIBILITY], [InterviewTopic.PAYMENT], asked=3
    )

    assert question_progress(coverage, InterviewTopic.FEASIBILITY) == (3, 3)


def test_total_is_capped_at_the_question_limit() -> None:
    coverage = _coverage(TOPICS, [], asked=7)

    assert question_progress(coverage, InterviewTopic.OTHER) == (7, 8)
