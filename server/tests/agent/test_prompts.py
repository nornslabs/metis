"""The prompt loader: latest version by default, a named version on request, clear failures."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from metis.agent.prompts import PromptNotFoundError, load_prompt
from metis.agent.supervisor import Specialist

if TYPE_CHECKING:
    from pathlib import Path


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


def test_the_interviewer_prompt_offers_options_and_the_older_version_is_kept() -> None:
    latest = load_prompt("interviewer")

    assert "`options`" in latest
    assert latest == load_prompt("interviewer", 3)
    assert "`options`" not in load_prompt("interviewer", 2)


def test_the_planner_prompt_offers_linear_reads_and_the_older_version_is_kept() -> None:
    latest = load_prompt("planner")

    assert all(tool in latest for tool in ("list_teams", "list_projects", "list_issues"))
    assert latest == load_prompt("planner", 3)
    assert "list_teams" not in load_prompt("planner", 2)
