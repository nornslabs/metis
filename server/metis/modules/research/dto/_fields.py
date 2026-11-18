"""Field types shared by the research DTOs: trimmed texts, web URLs and 0–1 fractions."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

from metis.modules.research.helpers.domain import web_url

FRACTION_DECIMALS = 2


def _round_fraction(value: float) -> float:
    return round(value, FRACTION_DECIMALS)


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Pricing = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1_000)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000)]
Summary = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4_000)]
WebUrl = Annotated[str, AfterValidator(web_url)]
# 0–1 with two decimals, as stored in ``numeric(3,2)``.
Fraction = Annotated[float, Field(ge=0, le=1), AfterValidator(_round_fraction)]
