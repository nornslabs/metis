"""The gate eval harness: case files, the recorded run, and that a wrong verdict is reported.

Seam: ``evals.run_gates`` (``evaluate`` and ``main``). No database or Redis is needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.gate_cases import CASES_PATH, GateCaseFileError, load_gate_cases
from evals.run_gates import (
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


def test_the_frozen_cases_cover_good_generic_inferable_and_duplicate_questions() -> None:
    cases = load_gate_cases()

    assert {c.expect for c in cases} == {"ask", "revise", "answered"}
    assert {c.id.split("-")[0] for c in cases} == {"good", "generic", "inferable", "duplicate"}
    assert len({c.idea.title for c in cases}) >= 3


def test_the_recorded_run_passes_every_case(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--recorded", "--min-pass-rate", "1"]) == EXIT_OK
    assert "Pass rate: 14/14" in capsys.readouterr().out


async def test_a_wrong_verdict_is_reported_as_a_failure() -> None:
    cases = load_gate_cases()
    verdicts = load_verdicts()
    verdicts[("generic-pain", "output")] = "PASS"  # a judge that lets a generic question through
    model = RecordedChat(verdicts, {c.question: c.id for c in cases})

    results = await evaluate(cases, model, repeat=1)

    failed = [r.case_id for r in results if not r.passed]
    assert failed == ["generic-pain"]
    assert pass_rate(results) < 1


def test_a_run_below_the_pass_rate_exits_with_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [
        json.loads(line)
        for line in Path(CASES_PATH.parent / "recorded.jsonl").read_text().splitlines()
    ]
    for row in rows:
        if row["gate"] == "output":
            row["verdict"] = "PASS"
    path = tmp_path / "all-pass.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    assert main(["--recorded", str(path), "--min-pass-rate", "1"]) == EXIT_BELOW_THRESHOLD
    assert "Failures:" in capsys.readouterr().out


def test_an_unknown_case_id_exits_with_a_setup_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--recorded", "--cases", "no-such-case"]) == EXIT_SETUP
    assert "unknown case id(s): no-such-case" in capsys.readouterr().err


def test_a_real_run_without_model_settings_names_what_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in MODEL_VARS:
        monkeypatch.delenv(name, raising=False)

    assert main([]) == EXIT_SETUP
    err = capsys.readouterr().err
    assert all(name in err for name in MODEL_VARS)


def test_a_bad_case_line_is_named_by_its_line_number(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text('{"id": "x"}\n', encoding="utf-8")

    with pytest.raises(GateCaseFileError, match="line 1"):
        load_gate_cases(path)


def test_a_repeated_case_id_is_rejected(tmp_path: Path) -> None:
    line = CASES_PATH.read_text(encoding="utf-8").splitlines()[0]
    path = tmp_path / "cases.jsonl"
    path.write_text(f"{line}\n{line}\n", encoding="utf-8")

    with pytest.raises(GateCaseFileError, match="repeated case id"):
        load_gate_cases(path)
