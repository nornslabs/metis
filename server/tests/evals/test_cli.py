"""The command line's setup errors: exit code 2 and a message, before any database call."""

from __future__ import annotations

import pytest

from evals.run_scoring import EXIT_SETUP, main

MODEL_VARS = ("EVAL_LLM_BASE_URL", "EVAL_LLM_API_KEY", "EVAL_LLM_MODEL")


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
    assert "--recorded" in err


def test_a_repeat_below_one_is_a_setup_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--recorded", "--repeat", "0"]) == EXIT_SETUP
    assert "--repeat must be at least 1" in capsys.readouterr().err
