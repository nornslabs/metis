"""The text the export puts in Linear (SHIP-253): names and descriptions, as pure functions."""

from __future__ import annotations

from uuid import uuid4

from metis.agent.tools.export_project import (
    MAX_DESCRIPTION_CHARS,
    MAX_NAME_CHARS,
    MAX_SPEC_SUMMARY_CHARS,
    ProjectScore,
    idea_url,
    milestone_description,
    milestone_name,
    project_description,
    spec_summary,
)

URL = "https://metis.test/ideas/1"


def test_a_milestone_is_named_by_its_one_based_place_in_the_plan() -> None:
    assert milestone_name(0, "Foundations") == "Phase 1 — Foundations"
    assert milestone_name(3, "  Launch ") == "Phase 4 — Launch"


def test_a_milestone_description_holds_the_goal_and_the_exit_criteria() -> None:
    text = milestone_description("Ship the core.", "Demo works.")

    assert "Ship the core." in text and "Demo works." in text
    assert text.index("Ship the core.") < text.index("Demo works.")


def test_the_project_description_links_back_and_shows_summary_score_and_band() -> None:
    text = project_description(
        url=URL,
        spec_text="# Spec\n\n## Problem\n\nLeads get lost.\n\nSecond line.",
        score=ProjectScore(total=78, band="build"),
        plan_version=3,
    )

    assert f"[Metis]({URL})" in text
    assert "Leads get lost. Second line." in text
    assert "#" not in text
    assert "78/100 (build)" in text
    assert "Plan version 3." in text


def test_the_project_description_leaves_out_the_score_when_there_is_none() -> None:
    text = project_description(url=URL, spec_text="", score=None, plan_version=1)

    assert "Score" not in text and "Spec" not in text
    assert f"[Metis]({URL})" in text


def test_long_text_is_cut_to_the_limits_with_an_ellipsis() -> None:
    assert len(milestone_name(0, "x" * 1000)) == MAX_NAME_CHARS
    assert milestone_name(0, "x" * 1000).endswith("…")
    assert len(milestone_description("g" * 9000, "e")) <= MAX_DESCRIPTION_CHARS
    assert len(spec_summary("word " * 1000)) <= MAX_SPEC_SUMMARY_CHARS


def test_the_idea_url_has_one_slash_whatever_the_base() -> None:
    idea_id = uuid4()

    assert idea_url("https://metis.test/", idea_id) == f"https://metis.test/ideas/{idea_id}"
    assert idea_url("https://metis.test", idea_id) == f"https://metis.test/ideas/{idea_id}"
