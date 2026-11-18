"""The research module's domain normalization: the key competitors are deduped on."""

from __future__ import annotations

import pytest

from metis.core.errors import InvalidInputError
from metis.modules.research.helpers.domain import normalize_domain


@pytest.mark.parametrize(
    ("url", "domain"),
    [
        ("https://acme.com", "acme.com"),
        ("https://www.acme.com/pricing?plan=pro#faq", "acme.com"),
        ("http://WWW.Acme.COM:8080/", "acme.com"),
        ("acme.com", "acme.com"),
        ("www.acme.com/about", "acme.com"),
        ("  https://acme.com/  ", "acme.com"),
        ("https://docs.acme.com", "docs.acme.com"),
        ("https://acme.com.", "acme.com"),
        ("https://bücher.example", "xn--bcher-kva.example"),
    ],
)
def test_normalize_domain_keeps_only_the_lowercased_host_without_www(url: str, domain: str) -> None:
    assert normalize_domain(url) == domain


@pytest.mark.parametrize("url", ["", "   ", "https://", "https:///path", "mailto:me@acme.com"])
def test_a_url_without_a_host_is_rejected(url: str) -> None:
    with pytest.raises(InvalidInputError):
        normalize_domain(url)
