"""``safe_relative_path``: only same-site relative paths survive; anything else is ``/``."""

from __future__ import annotations

import pytest

from metis.helpers.redirects import MAX_REDIRECT_LENGTH, safe_relative_path


@pytest.mark.parametrize(
    "path",
    ["/", "/ideas", "/ideas/123?tab=score", "/ideas/123#spec", "/settings/keys?kind=llm"],
)
def test_relative_paths_are_kept(path: str) -> None:
    assert safe_relative_path(path) == path


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "https://evil.example",
        "http://evil.example/ideas",
        "//evil.example",
        "///evil.example",
        "/\\evil.example",
        "\\\\evil.example",
        "/ideas\\..\\evil",
        "javascript:alert(1)",
        "ideas/123",
        "/ideas\n/evil",
        "/ideas\t",
        "/ideas\x00",
        "/" + "a" * MAX_REDIRECT_LENGTH,
    ],
)
def test_anything_else_falls_back_to_root(value: str | None) -> None:
    assert safe_relative_path(value) == "/"
