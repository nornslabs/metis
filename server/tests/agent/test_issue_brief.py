"""The issue brief (SHIP-459): required sections and fitting into Linear's limit. Pure."""

from __future__ import annotations

from metis.agent.tools.issue_brief import fit_brief, missing_sections, parse_sections

FULL = (
    "## Goal\nShip the thing.\n\n"
    "## Context\nBackground the developer needs.\n\n"
    "## Requirements\n1. Do A.\n2. Do B.\n\n"
    "## Out of scope\nNo C.\n\n"
    "## Acceptance criteria\n- A works.\n\n"
    "## Dependencies\nNone"
)


def test_a_full_brief_has_no_missing_sections() -> None:
    assert missing_sections(FULL) == ()


def test_missing_and_empty_sections_are_named_in_brief_order() -> None:
    description = "## Goal\n\n## Requirements\n1. Do A."

    assert missing_sections(description) == ("Goal", "Acceptance criteria")


def test_headings_match_ignoring_case_and_a_trailing_colon() -> None:
    description = "## goal:\nx\n\n## REQUIREMENTS\n1. y\n\n## Acceptance Criteria\n- z"

    assert missing_sections(description) == ()


def test_free_text_lacks_every_required_section() -> None:
    assert missing_sections("Do it. Done when it works.") == (
        "Goal",
        "Requirements",
        "Acceptance criteria",
    )


def test_text_before_the_first_heading_is_kept_as_its_own_section() -> None:
    sections = parse_sections("Intro line.\n\n## Goal\nx")

    assert [s.name for s in sections] == ["", "goal"]


def test_a_brief_that_fits_is_returned_whole() -> None:
    assert fit_brief(FULL, 4_000) == FULL


def test_agent_notes_are_wrapped_in_a_collapsible_block() -> None:
    brief = FULL + "\n\n## Agent notes\nTouches export_issue.py."

    fitted = fit_brief(brief, 4_000)

    assert fitted.endswith(">>> Agent notes\n\nTouches export_issue.py.\n\n>>>")


def test_agent_notes_go_first_when_the_brief_is_too_long() -> None:
    brief = FULL + "\n\n## Agent notes\n" + "n" * 500

    fitted = fit_brief(brief, len(FULL) + 20)

    assert fitted == FULL
    assert "Agent notes" not in fitted


def test_context_goes_next_and_acceptance_criteria_survive() -> None:
    brief = FULL.replace("Background the developer needs.", "c" * 500)

    fitted = fit_brief(brief, len(FULL) - 20)

    assert "## Context" not in fitted
    assert "## Acceptance criteria\n- A works." in fitted
    assert "## Goal\nShip the thing." in fitted
    assert len(fitted) <= len(FULL) - 20


def test_dependencies_go_after_context_and_before_requirements() -> None:
    brief = FULL.replace("Background the developer needs.", "c" * 500).replace("None", "d" * 500)

    fitted = fit_brief(brief, len(FULL) - 20)

    assert "## Context" not in fitted and "## Dependencies" not in fitted
    assert "## Requirements\n1. Do A.\n2. Do B." in fitted


def test_requirements_are_cut_last_and_goal_and_acceptance_stay_whole() -> None:
    brief = "## Goal\nG.\n\n## Requirements\n" + "r" * 1_000 + "\n\n## Acceptance criteria\n- ok"

    fitted = fit_brief(brief, 200)

    assert len(fitted) <= 200
    assert "## Goal\nG." in fitted
    assert fitted.endswith("## Acceptance criteria\n- ok")


def test_free_text_is_only_cut_to_the_limit() -> None:
    fitted = fit_brief("x" * 300, 100)

    assert len(fitted) == 100 and fitted.endswith("…")
