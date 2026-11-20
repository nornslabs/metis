"""The report a developer reads: table, failures, flags and the two rates."""

from __future__ import annotations

from decimal import Decimal

from evals.report import CaseOutcome, RunOutcome, Usage, band_accuracy, format_report, pass_rate
from metis.modules.scoring import ScoreBand

GOOD = RunOutcome(ScoreBand.BUILD, 80, ())


def _outcomes() -> list[CaseOutcome]:
    wrong = RunOutcome(ScoreBand.PROMISING, 60, ("band promising, expected build",))
    failed = RunOutcome(None, None, (), error_code="score.invalid_submission")
    return [
        CaseOutcome("clear-build", ScoreBand.BUILD, (GOOD, GOOD), ()),
        CaseOutcome("noisy-build", ScoreBand.BUILD, (GOOD, GOOD), ("timing unstable (6-8)",)),
        CaseOutcome("wrong-band", ScoreBand.BUILD, (wrong, GOOD), ()),
        CaseOutcome("no-score", ScoreBand.BUILD, (failed, GOOD), ()),
    ]


def test_pass_rate_counts_cases_whose_every_run_passed_and_flags_do_not_fail() -> None:
    assert pass_rate(_outcomes()) == 0.5


def test_band_accuracy_counts_runs_with_the_expected_band() -> None:
    assert band_accuracy(_outcomes()) == 6 / 8


def test_an_empty_run_has_zero_rates() -> None:
    assert pass_rate([]) == 0.0
    assert band_accuracy([]) == 0.0


def test_the_report_lists_each_failure_with_its_run_and_reason() -> None:
    report = format_report(_outcomes(), model="m", prompt="scorer.v2.md", usage=None)

    assert "wrong-band: run 1: band promising, expected build" in report
    assert "no-score: run 1: no score stored (score.invalid_submission)" in report


def test_the_report_marks_unstable_cases_and_names_the_flag() -> None:
    report = format_report(_outcomes(), model="m", prompt="scorer.v2.md", usage=None)

    assert "noisy-build" in report
    assert "PASS (unstable)" in report
    assert "noisy-build: timing unstable (6-8)" in report


def test_the_report_ends_with_rates_prompt_model_and_cost() -> None:
    usage = Usage(1000, 200, Decimal("0.0123"))

    report = format_report(_outcomes(), model="gpt-x", prompt="scorer.v2.md", usage=usage)

    assert "Pass rate: 2/4 = 50%" in report
    assert "Band accuracy: 75%" in report
    assert "Prompt: scorer.v2.md   Model: gpt-x" in report
    assert "Tokens: 1000 in / 200 out   Cost: $0.0123" in report


def test_an_unknown_cost_is_shown_as_unknown() -> None:
    report = format_report(_outcomes(), model="m", prompt="p", usage=Usage(1, 1, None))

    assert "Cost: unknown" in report
