"""Field types shared by the scoring DTOs: trimmed texts, web URLs, marks and fractions."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator, Field, StringConstraints

FRACTION_DECIMALS = 2
MAX_URL_LENGTH = 2_048
WEB_SCHEMES = frozenset({"http", "https"})
MAX_RAW = 10


def _round_fraction(value: float) -> float:
    return round(value, FRACTION_DECIMALS)


def _web_url(value: str) -> str:
    url = value.strip()
    if len(url) > MAX_URL_LENGTH:
        raise ValueError(f"must be at most {MAX_URL_LENGTH} characters")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise ValueError("must be an http(s) URL with a host") from exc
    if parts.scheme not in WEB_SCHEMES or not parts.hostname:
        raise ValueError("must be an http(s) URL with a host")
    return url


Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)]
Quote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2_000)]
WebUrl = Annotated[str, AfterValidator(_web_url)]
Mark = Annotated[int, Field(ge=0, le=MAX_RAW, strict=True)]
# 0–1 with two decimals, as stored in ``numeric(3,2)``.
Fraction = Annotated[float, Field(ge=0, le=1), AfterValidator(_round_fraction)]
