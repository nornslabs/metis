"""String clean-up helpers for Pydantic validators."""

from __future__ import annotations

import pytest

from metis.helpers.text import strip, strip_to_none


@pytest.mark.parametrize(("raw", "expected"), [("  a b  ", "a b"), ("", ""), (None, None), (3, 3)])
def test_strip_trims_strings_and_passes_other_values(raw: object, expected: object) -> None:
    assert strip(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"), [("  a  ", "a"), ("   ", None), ("", None), (None, None)]
)
def test_strip_to_none_turns_blank_strings_into_none(raw: object, expected: object) -> None:
    assert strip_to_none(raw) == expected
