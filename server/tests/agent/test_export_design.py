"""The Design line and the room it takes in an issue description (pure functions)."""

from __future__ import annotations

from metis.agent.tools.export_issue import (
    DESIGN_RESERVE_CHARS,
    brief_room,
    design_line,
    issue_description,
)
from metis.agent.tools.export_project import MAX_DESCRIPTION_CHARS, MAX_NAME_CHARS, hld_title

URL = "https://linear.app/document/doc-1"


def test_the_design_line_names_the_link_and_the_component() -> None:
    assert design_line(URL, "Leads API") == f"HLD: {URL} · Component: Leads API"


def test_the_design_line_is_only_the_link_without_a_component() -> None:
    assert design_line(URL, None) == f"HLD: {URL}"


def test_a_description_ends_with_the_design_line_then_the_footer() -> None:
    text = issue_description("## Goal\n\nDo it.", "http://x/ideas/1", design_line(URL, "Web"))

    assert text.splitlines()[-3:] == [
        f"HLD: {URL} · Component: Web",
        "---",
        "Created by [Metis](http://x/ideas/1)",
    ]


def test_without_an_hld_the_description_has_no_design_line() -> None:
    assert "HLD:" not in issue_description("## Goal\n\nDo it.", "http://x/ideas/1")


def test_the_brief_leaves_room_for_the_design_line() -> None:
    assert brief_room(design_chars=0) == brief_room() - DESIGN_RESERVE_CHARS - 2


def test_a_long_brief_with_a_design_line_stays_within_the_limit() -> None:
    brief = (
        "## Goal\n\nDo it.\n\n## Requirements\n\n"
        + "step\n" * 2000
        + ("\n## Acceptance criteria\n\n- it works")
    )

    text = issue_description(brief, "http://x/ideas/1", design_line(URL, "Web"))

    assert len(text) <= MAX_DESCRIPTION_CHARS
    assert "- it works" in text


def test_the_document_title_keeps_its_suffix_for_a_long_project_name() -> None:
    title = hld_title("word " * 40)

    assert title.endswith(" HLD")
    assert len(title) <= MAX_NAME_CHARS
