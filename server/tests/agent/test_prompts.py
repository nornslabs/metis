"""The prompt loader: latest version by default, a named version on request, clear failures."""

from __future__ import annotations

from pathlib import Path

import pytest

from metis.agent.prompts import PromptNotFoundError, load_prompt, load_specialist_prompt
from metis.agent.supervisor import Specialist


@pytest.fixture
def prompts(tmp_path: Path) -> Path:
    (tmp_path / "scorer.v1.md").write_text("first")
    (tmp_path / "scorer.v2.md").write_text("second")
    (tmp_path / "scorer.v10.md").write_text("tenth")
    (tmp_path / "scorer_extra.v1.md").write_text("other prompt")
    return tmp_path


def test_returns_the_latest_version_by_default(prompts: Path) -> None:
    assert load_prompt("scorer", directory=prompts) == "tenth"


def test_returns_a_named_version(prompts: Path) -> None:
    assert load_prompt("scorer", 2, directory=prompts) == "second"


def test_unknown_version_names_the_available_ones(prompts: Path) -> None:
    with pytest.raises(PromptNotFoundError, match=r"no version 3.*\[1, 2, 10\]"):
        load_prompt("scorer", 3, directory=prompts)


def test_unknown_prompt_fails(prompts: Path) -> None:
    with pytest.raises(PromptNotFoundError, match="advisor"):
        load_prompt("advisor", directory=prompts)


@pytest.mark.parametrize("specialist", list(Specialist))
def test_every_specialist_ships_a_first_prompt(specialist: Specialist) -> None:
    assert load_prompt(specialist.value, 1).strip()


def test_the_researcher_prompt_names_the_tools_it_may_use() -> None:
    prompt = load_prompt("researcher")

    assert all(tool in prompt for tool in ("kb_lookup", "save_research_item", "finish_research"))


def test_the_researcher_prompt_explains_refused_calls_and_the_older_version_is_kept() -> None:
    latest = load_prompt("researcher")

    assert "refused" in latest and "skipped" in latest
    assert latest == load_prompt("researcher", 3)
    assert "refused" not in load_prompt("researcher", 2)


def test_the_interviewer_prompt_offers_options_and_the_older_version_is_kept() -> None:
    latest = load_prompt("interviewer")

    assert "`options`" in latest
    assert latest == load_prompt("interviewer", 4)
    assert "`options`" in load_prompt("interviewer", 3)
    assert "`options`" not in load_prompt("interviewer", 2)


def test_the_planner_prompt_offers_linear_reads_and_the_older_version_is_kept() -> None:
    latest = load_prompt("planner")

    assert all(tool in latest for tool in ("list_teams", "list_projects", "list_issues"))
    assert latest == load_prompt("planner", 4)
    assert "list_teams" in load_prompt("planner", 3)
    assert "list_teams" not in load_prompt("planner", 2)


def test_the_planner_prompt_asks_for_issue_briefs_and_the_older_version_is_kept() -> None:
    latest = load_prompt("planner")

    assert all(f"`## {name}`" in latest for name in ("Goal", "Requirements", "Acceptance criteria"))
    assert "Out of scope" in latest and "Agent notes" in latest
    assert "## Goal" not in load_prompt("planner", 3)


def test_the_soul_ships_and_leads_every_specialist_prompt_that_calls_a_model() -> None:
    soul = load_prompt("soul")

    for name in ("interviewer", "researcher", "scorer", "advisor", "architect", "planner"):
        assert load_specialist_prompt(name).startswith(soul)
        assert load_specialist_prompt(name).endswith(load_prompt(name))


def test_the_soul_states_the_voice_rules() -> None:
    soul = load_prompt("soul").lower()

    assert all(word in soul for word in ("one short line", "one thing at a time", "emoji"))
    assert "never flatter" in soul and "never as a verdict" in soul


def test_the_integrator_makes_no_model_call_so_its_prompt_has_no_soul() -> None:
    from metis.agent.specialists import integrator

    assert "load_specialist_prompt" not in open(integrator.__file__).read()
