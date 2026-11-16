"""Token prices and the cost of a call. No built-in price list: unknown models have no cost."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from metis.helpers.dto import FrozenModel

TOKENS_PER_PRICE_UNIT = 1_000_000


class ModelPrice(FrozenModel):
    """What one model costs, in USD per million tokens."""

    input_per_million_usd: Decimal = Field(ge=0)
    output_per_million_usd: Decimal = Field(ge=0)


def cost_usd(price: ModelPrice | None, input_tokens: int, output_tokens: int) -> Decimal | None:
    """The cost of one call, or ``None`` when no price is known (never a guess)."""
    if price is None:
        return None
    return (
        price.input_per_million_usd * input_tokens + price.output_per_million_usd * output_tokens
    ) / TOKENS_PER_PRICE_UNIT
