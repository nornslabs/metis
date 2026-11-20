"""The rubric's weight math, rounding and band edges (pure functions, no database)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from metis.modules.scoring.dto.enums import ScoreBand
from metis.modules.scoring.service.rubric import band_for, total_from, weighted_points


@pytest.mark.parametrize(
    ("raw", "weight", "expected"),
    [(10, 25, "25.00"), (0, 25, "0.00"), (7, 15, "10.50"), (3, 10, "3.00"), (5, 25, "12.50")],
)
def test_weighted_points_are_raw_over_ten_times_the_weight(
    raw: int, weight: int, expected: str
) -> None:
    assert weighted_points(raw, weight) == Decimal(expected)


@pytest.mark.parametrize(
    ("points", "expected"),
    [
        (["54.40"], 54),
        (["54.50"], 55),
        (["74.49"], 74),
        (["74.50"], 75),
        (["0"], 0),
        (["100"], 100),
    ],
)
def test_total_rounds_half_up(points: list[str], expected: int) -> None:
    assert total_from(Decimal(p) for p in points) == expected


@pytest.mark.parametrize(
    ("total", "band"),
    [
        (0, ScoreBand.ADVISE),
        (54, ScoreBand.ADVISE),
        (55, ScoreBand.PROMISING),
        (74, ScoreBand.PROMISING),
        (75, ScoreBand.BUILD),
        (100, ScoreBand.BUILD),
    ],
)
def test_band_edges(total: int, band: ScoreBand) -> None:
    assert band_for(total) is band
