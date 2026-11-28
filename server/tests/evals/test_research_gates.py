"""The Researcher's gate evals: case file, recorded run, and that a wrong verdict is reported.

Seam: ``evals.run_gates`` (``evaluate`` and ``main``) with the research suite. No database or
Redis is needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.gate_cases import (
    RESEARCH_CASES_PATH,
    RESEARCH_RECORDED_PATH,
    GateCaseFileError,
    load_research_gate_cases,
)
from evals.research_gate_eval import RecordedResearchChat, run_research_case_once
from evals.run_gates import EXIT_OK, EXIT_SETUP, evaluate, load_verdicts, main


def test_the_frozen_cases_cover_passing_vague_redundant_and_repeated_calls() -> None:
    cases = load_research_gate_cases()

    assert {c.expect for c in cases} == {"run", "refuse"}
    assert {c.tool for c in cases} == {"web_search_exa", "web_fetch_exa"}
    assert any(c.kb_matches for c in cases)
    assert any(c.earlier_queries for c in cases)
    assert any(c.fetched_urls or c.saved_urls for c in cases)
    assert len({c.idea.title for c in cases}) >= 3


def test_the_recorded_run_passes_every_case(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["--specialist", "researcher", "--recorded", "--min-pass-rate", "1"]

    assert main(args) == EXIT_OK
    assert "Pass rate: 13/13" in capsys.readouterr().out


def test_both_suites_run_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--recorded", "--min-pass-rate", "1"]) == EXIT_OK
    assert "Pass rate: 27/27" in capsys.readouterr().out


def test_a_recorded_file_needs_one_specialist(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--recorded", str(RESEARCH_RECORDED_PATH)]) == EXIT_SETUP
    assert "--specialist" in capsys.readouterr().err


async def test_a_judge_that_lets_a_vague_search_through_is_reported_as_a_failure() -> None:
    cases = load_research_gate_cases()
    verdicts = load_verdicts(RESEARCH_RECORDED_PATH)
    verdicts[("refuse-vague-competitors", "input")] = "PASS"
    model = RecordedResearchChat(verdicts, cases)

    results = await evaluate(cases, model, 1, run_research_case_once)

    assert [r.case_id for r in results if not r.passed] == ["refuse-vague-competitors"]


async def test_a_repeated_search_is_refused_by_the_code_check_without_a_judge_verdict() -> None:
    cases = load_research_gate_cases()
    model = RecordedResearchChat({}, cases)  # no verdicts at all: any judge call would raise
    repeated = next(c for c in cases if c.id == "refuse-duplicate-search")

    assert await run_research_case_once(repeated, model) == "refuse"


def test_a_bad_case_line_is_named_by_its_line_number(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text('{"id": "x"}\n', encoding="utf-8")

    with pytest.raises(GateCaseFileError, match="line 1"):
        load_research_gate_cases(path)


def test_two_cases_for_the_same_call_are_rejected(tmp_path: Path) -> None:
    row = json.loads(RESEARCH_CASES_PATH.read_text(encoding="utf-8").splitlines()[0])
    path = tmp_path / "cases.jsonl"
    path.write_text(f"{json.dumps(row)}\n{json.dumps({**row, 'id': 'other'})}\n", encoding="utf-8")

    with pytest.raises(GateCaseFileError, match="share an idea, a tool and a target"):
        load_research_gate_cases(path)
