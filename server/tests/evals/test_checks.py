"""The pure checks: one test per way a verdict can be wrong, and what counts as unstable."""

from __future__ import annotations

from evals.checks import check_run, unstable_flags
from metis.modules.scoring import ScoreBand, ScoreParam
from tests.evals.eval_helpers import OTHER, SOURCE, case, param, score_run


def test_a_verdict_that_meets_every_expectation_has_no_failures() -> None:
    expected = case(total=(55, 70), params={ScoreParam.UNIQUENESS: (5, 7)})

    assert check_run(expected, score_run()) == ()


def test_a_wrong_band_is_reported_with_both_bands() -> None:
    failures = check_run(case(band=ScoreBand.BUILD), score_run(band=ScoreBand.PROMISING))

    assert failures == ("band promising, expected build",)


def test_a_total_outside_its_range_is_reported() -> None:
    failures = check_run(case(total=(60, 70)), score_run(total=58))

    assert failures == ("total 58 outside 60-70",)


def test_a_mark_outside_its_range_is_reported() -> None:
    failures = check_run(case(params={ScoreParam.TIMING: (7, 9)}), score_run())

    assert failures == ("timing 6 outside 7-9",)


def test_a_mark_left_out_of_the_score_is_reported_missing() -> None:
    marks = {name: 6 for name in ScoreParam if name is not ScoreParam.VALUE}

    failures = check_run(case(params={ScoreParam.VALUE: (4, 8)}), score_run(marks))

    assert failures == ("value missing",)


def test_evidence_that_is_not_a_source_of_the_snapshot_is_reported() -> None:
    bad = param(ScoreParam.VALUE, 6, url=OTHER)

    failures = check_run(case(), score_run(overrides={ScoreParam.VALUE: bad}))

    assert failures == (f"value cites {OTHER}, not a source of the research",)


def test_a_source_url_is_matched_after_trimming_a_slash_and_fragment() -> None:
    cited = param(ScoreParam.VALUE, 6, url=f"{SOURCE}/#section")

    assert check_run(case(), score_run(overrides={ScoreParam.VALUE: cited})) == ()


def test_a_mark_with_no_evidence_and_no_admission_is_reported() -> None:
    bare = param(ScoreParam.VALUE, 6, url=None)

    failures = check_run(case(), score_run(overrides={ScoreParam.VALUE: bare}))

    assert failures == ("value has no evidence",)


def test_no_evidence_is_accepted_when_stated_and_not_confident() -> None:
    gap = param(ScoreParam.VALUE, 4, no_evidence=True, confidence=0.2)

    assert check_run(case(), score_run(overrides={ScoreParam.VALUE: gap})) == ()


def test_no_evidence_with_high_confidence_is_reported() -> None:
    gap = param(ScoreParam.VALUE, 4, no_evidence=True, confidence=0.9)

    failures = check_run(case(), score_run(overrides={ScoreParam.VALUE: gap}))

    assert failures == ("value says no evidence but cites sources or is confident",)


def test_a_mark_with_a_blank_reason_is_reported() -> None:
    blank = param(ScoreParam.VALUE, 6, reason="  ")

    failures = check_run(case(), score_run(overrides={ScoreParam.VALUE: blank}))

    assert failures == ("value has no reason",)


def test_marks_one_apart_are_not_flagged() -> None:
    first = score_run()
    second = score_run(dict.fromkeys(ScoreParam, 7))

    assert unstable_flags([first, second]) == ()


def test_a_mark_two_apart_is_flagged_with_its_span() -> None:
    first = score_run()
    second = score_run(overrides={ScoreParam.TIMING: param(ScoreParam.TIMING, 8)})

    assert unstable_flags([first, second]) == ("timing unstable (6-8)",)


def test_a_band_that_changes_between_runs_is_flagged() -> None:
    first = score_run(band=ScoreBand.PROMISING)
    second = score_run(band=ScoreBand.BUILD)

    assert unstable_flags([first, second]) == ("band changed between runs",)


def test_a_single_run_has_nothing_to_compare() -> None:
    assert unstable_flags([score_run()]) == ()
