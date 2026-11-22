"""Rendering and parsing a spec's markdown, and comparing two versions section by section."""

from __future__ import annotations

from metis.modules.ideas import SpecSection
from metis.modules.ideas.dto import SECTION_HEADINGS, DiffStatus
from metis.modules.ideas.helpers.spec_markdown import (
    diff_sections,
    parse_sections,
    render_markdown,
)

FULL = {section.value: f"Text of {section.value}." for section in SpecSection}


def test_a_rendered_spec_has_every_heading_in_template_order() -> None:
    markdown = render_markdown(FULL)

    positions = [markdown.index(f"## {heading}") for heading in SECTION_HEADINGS.values()]
    assert positions == sorted(positions)


def test_an_empty_section_is_written_as_none() -> None:
    markdown = render_markdown({**FULL, "risks": "  "})

    assert "## Risks\n\nNone." in markdown


def test_rendering_then_parsing_returns_the_sections() -> None:
    assert parse_sections(render_markdown(FULL)) == FULL


def test_headings_match_without_regard_to_case_and_text_before_the_first_is_ignored() -> None:
    sections = parse_sections("Intro line.\n\n## PROBLEM\n\nIt hurts.\n\n## target users\nSolo.")

    assert sections == {"problem": "It hurts.", "target_users": "Solo."}


def test_text_under_an_unknown_heading_is_kept_under_its_slug() -> None:
    sections = parse_sections("## Pricing & plans\n\n5 a month.\n\n### Sub heading\nstays")

    assert sections == {"pricing_plans": "5 a month.\n\n### Sub heading\nstays"}


def test_custom_sections_are_rendered_after_the_template() -> None:
    markdown = render_markdown({**FULL, "pricing_plans": "5 a month."})

    assert markdown.rstrip().endswith("## Pricing plans\n\n5 a month.")


def test_a_diff_says_what_changed_in_each_section() -> None:
    a = {**FULL, "legacy": "Old."}
    b = {**FULL, "solution": "Different.", "extra": "New."}
    del b["risks"]

    diff = {d.section: d.status for d in diff_sections(a, b)}

    assert diff["problem"] is DiffStatus.UNCHANGED
    assert diff["solution"] is DiffStatus.CHANGED
    assert diff["risks"] is DiffStatus.REMOVED
    assert diff["extra"] is DiffStatus.ADDED
    assert diff["legacy"] is DiffStatus.REMOVED


def test_a_diff_lists_template_sections_first_and_in_order() -> None:
    order = [d.section for d in diff_sections({**FULL, "z": "1"}, {**FULL, "a": "2"})]

    assert order[: len(SpecSection)] == [section.value for section in SpecSection]
    assert order[len(SpecSection) :] == ["z", "a"]


def test_whitespace_alone_is_not_a_change() -> None:
    diff = diff_sections({"problem": "Same."}, {"problem": "  Same.\n"})

    assert diff[0].status is DiffStatus.UNCHANGED
