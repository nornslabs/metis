"""LLM usage DTOs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from metis.helpers.dto import FrozenModel

if TYPE_CHECKING:
    from decimal import Decimal
    from uuid import UUID


class NewLlmUsage(FrozenModel):
    """One completed LLM call to record. ``cost_usd`` is ``None`` when no price is known."""

    run_id: UUID
    model: str = Field(min_length=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=0)
