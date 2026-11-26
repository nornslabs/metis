"""File-name slugs from idea titles."""

from __future__ import annotations

import pytest

from metis.helpers.slug import FALLBACK_SLUG, SLUG_LIMIT, title_slug


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Pocket CRM", "pocket-crm"),
        ("  A  tiny -- CRM!  ", "a-tiny-crm"),
        ("Café Ünïcode 2", "caf-n-code-2"),
    ],
)
def test_a_title_becomes_lowercase_words_joined_by_single_dashes(title: str, expected: str) -> None:
    assert title_slug(title) == expected


@pytest.mark.parametrize("title", ["", "   ", "!!!", "日本語", '"; rm -rf /\r\n'])
def test_a_title_with_nothing_usable_in_it_gives_the_fallback_or_a_safe_slug(title: str) -> None:
    slug = title_slug(title)

    assert slug.isascii()
    assert all(char.isalnum() or char == "-" for char in slug)
    assert slug


def test_a_title_with_nothing_but_symbols_gives_the_fallback() -> None:
    assert title_slug("!!!") == FALLBACK_SLUG


def test_a_long_title_is_cut_without_a_trailing_dash() -> None:
    slug = title_slug("word " * 30)

    assert len(slug) <= SLUG_LIMIT
    assert not slug.endswith("-")
