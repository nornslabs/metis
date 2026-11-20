"""The fixed rubric: which parameters there are and what each weighs."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import InvalidRubricError
from metis.modules.scoring import repo
from metis.modules.scoring.dto import Rubric, ScoreBand, ScoreParam
from metis.modules.scoring.dto._fields import MAX_RAW

EXPECTED_WEIGHT_TOTAL = 100
POINT_DECIMALS = Decimal("0.01")
BUILD_MIN_TOTAL = 75
PROMISING_MIN_TOTAL = 55


async def get_rubric(session: AsyncSession) -> Rubric:
    """The latest rubric version; a missing or inconsistent one is ``score.invalid_rubric``."""
    row = await repo.rubric.latest(session)
    if row is None:
        raise InvalidRubricError("no rubric version is stored")
    return rubric_of(row.id, row.weights)


def rubric_of(version: int, weights: dict[str, int]) -> Rubric:
    """``weights`` as a ``Rubric``, checked for all six parameters summing to 100."""
    if set(weights) != {p.value for p in ScoreParam} or sum(weights.values()) != (
        EXPECTED_WEIGHT_TOTAL
    ):
        raise InvalidRubricError(
            f"rubric version {version} does not hold the six weights summing to 100"
        )
    return Rubric(version=version, weights={p: weights[p.value] for p in ScoreParam})


def weighted_points(raw: int, weight: int) -> Decimal:
    """``raw / 10 * weight`` to two decimals, e.g. a 7 on a weight of 15 is ``10.50``."""
    return (Decimal(raw) * weight / MAX_RAW).quantize(POINT_DECIMALS, rounding=ROUND_HALF_UP)


def total_from(weighted: Iterable[Decimal]) -> int:
    """The sum of the weighted points, rounded half up to a whole number."""
    return int(sum(weighted, Decimal(0)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def band_for(total: int) -> ScoreBand:
    """``build`` from 75, ``promising`` from 55, else ``advise``; taken from the rounded total."""
    if total >= BUILD_MIN_TOTAL:
        return ScoreBand.BUILD
    if total >= PROMISING_MIN_TOTAL:
        return ScoreBand.PROMISING
    return ScoreBand.ADVISE
