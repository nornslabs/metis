"""Reading the component names out of an HLD's markdown."""

from __future__ import annotations

from metis.modules import ideas


def test_the_components_are_the_headings_under_mvp_components() -> None:
    md = (
        "## Overview\n\n### Not a component\n\n## MVP components\n\n### Leads API\n\ntext\n\n"
        "### Web app\n\n## How the components connect\n\n### Also not one"
    )

    assert ideas.component_names(md) == ("Leads API", "Web app")


def test_a_heading_inside_a_code_fence_is_not_a_component() -> None:
    md = "## MVP components\n\n### Real\n\n```\n### Fake\n```\n"

    assert ideas.component_names(md) == ("Real",)


def test_duplicates_ignoring_case_are_listed_once_and_no_section_gives_none() -> None:
    assert ideas.component_names("## MVP components\n\n### Api\n\n### API") == ("Api",)
    assert ideas.component_names("## Overview\n\nNothing here.") == ()


def test_a_component_is_matched_ignoring_case_and_returned_as_the_hld_spells_it() -> None:
    names = ("Leads API", "Web app")

    assert ideas.match_component(names, " web APP ") == "Web app"
    assert ideas.match_component(names, "Billing") is None
    assert ideas.match_component(names, None) is None
    assert ideas.match_component(names, "  ") is None
