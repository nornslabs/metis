"""The Advisor gate eval harness: case files, the recorded run, and that a wrong verdict shows.

Seam: ``evals.run_advice_gate`` (``evaluate`` and ``main``). No database or Redis is needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.advice_gate_cases import (
    CASES_PATH,
    RECORDED_PATH,
    AdviceGateCaseFileError,
    load_advice_gate_cases,
)
from evals.run_advice_gate import (
    EXIT_BELOW_THRESHOLD,
    EXIT_OK,
    EXIT_SETUP,
    RecordedChat,
    evaluate,
    load_verdicts,
    main,
    pass_rate,
)

MODEL_VARS = ("EVAL_LLM_BASE_URL", "EVAL_LLM_API_KEY", "EVAL_LLM_MODEL")


def test_the_frozen_cases_cover_every_way_a_suggestion_passes_or_is_rejected() -> None:
    cases = load_advice_gate_cases()

    assert {c.expect for c in cases} == {"pass", "reject"}
    assert {c.id.split("-")[0] for c in cases} == {
        "good",
        "generic",
        "duplicate",
        "wrong",
        "invented",
        "unsupported",
        "flattering",
    }
    assert len({c.idea.title for c in cases}) >= 3


def test_the_recorded_run_passes_every_case(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--recorded", "--min-pass-rate", "1"]) == EXIT_OK
    out = capsys.readouterr().out
    cases = load_advice_gate_cases()
    assert f"Pass rate: {len(cases)}/{len(cases)}" in out


def test_a_code_rejected_case_needs_no_recorded_verdict() -> None:
    cases = load_advice_gate_cases()
    recorded = {row["case"] for row in map(json.loads, RECORDED_PATH.read_text().splitlines())}

    by_code = {c.id for c in cases if c.reject_by == "code"}
    assert by_code and not by_code & recorded
    assert {c.id for c in cases if c.reject_by != "code"} <= recorded


async def test_a_judge_that_lets_a_generic_suggestion_through_is_reported_as_a_failure() -> None:
    cases = load_advice_gate_cases()
    verdicts = load_verdicts()
    verdicts["generic-improve-marketing"] = "PASS"
    model = RecordedChat(verdicts, {c.suggestion.title: c.id for c in cases})

    results = await evaluate(cases, model, repeat=1)

    assert [r.case_id for r in results if not r.passed] == ["generic-improve-marketing"]
    assert pass_rate(results) < 1


def test_a_run_below_the_pass_rate_exits_with_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [json.loads(line) for line in RECORDED_PATH.read_text().splitlines()]
    for row in rows:
        if row["case"] == "generic-improve-marketing":
            row["verdict"] = "PASS"
    broken = tmp_path / "recorded.jsonl"
    broken.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    code = main(["--recorded", str(broken), "--min-pass-rate", "1"])

    assert code == EXIT_BELOW_THRESHOLD
    assert "generic-improve-marketing" in capsys.readouterr().out


def test_a_run_without_a_model_exits_with_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in MODEL_VARS:
        monkeypatch.delenv(name, raising=False)

    assert main([]) == EXIT_SETUP
    assert "EVAL_LLM_BASE_URL" in capsys.readouterr().err


def test_an_unknown_case_id_exits_with_two(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--recorded", "--cases", "nope"]) == EXIT_SETUP
    assert "nope" in capsys.readouterr().err


def test_a_case_file_with_a_repeated_id_is_refused(tmp_path: Path) -> None:
    line = CASES_PATH.read_text().splitlines()[0]
    path = tmp_path / "cases.jsonl"
    path.write_text(f"{line}\n{line}\n", encoding="utf-8")

    with pytest.raises(AdviceGateCaseFileError, match="repeated"):
        load_advice_gate_cases(path)
