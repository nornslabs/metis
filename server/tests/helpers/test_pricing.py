"""Cost of a call: only from a configured price, never guessed."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from metis.helpers.pricing import ModelPrice, cost_usd

PRICE = ModelPrice(input_per_million_usd=Decimal("0.15"), output_per_million_usd=Decimal("0.60"))


def test_cost_is_none_without_a_price() -> None:
    assert cost_usd(None, 1_000, 1_000) is None


def test_cost_adds_input_and_output_at_their_rates_per_million_tokens() -> None:
    assert cost_usd(PRICE, 1_000_000, 500_000) == Decimal("0.45")


def test_zero_tokens_cost_nothing() -> None:
    assert cost_usd(PRICE, 0, 0) == Decimal(0)


def test_a_negative_price_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ModelPrice(input_per_million_usd=Decimal(-1), output_per_million_usd=Decimal(1))
