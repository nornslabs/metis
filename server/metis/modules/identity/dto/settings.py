"""Workspace settings DTOs: run limits, patches and the settings response."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import ConfigDict, Field, PlainSerializer, model_validator

from metis.helpers.dto import FrozenModel
from metis.modules.identity.dto.provider_keys import ProviderKeys

DEFAULT_RUN_BUDGET_USD = Decimal("2.00")
DEFAULT_MAX_STEPS = 50
MAX_RUN_BUDGET_USD = Decimal("100")
MAX_MAX_STEPS = 200
USD_DECIMAL_PLACES = 2

UsdAmount = Annotated[
    Decimal,
    Field(gt=0, le=MAX_RUN_BUDGET_USD, decimal_places=USD_DECIMAL_PLACES),
    PlainSerializer(float, return_type=float),
]
StepCount = Annotated[int, Field(ge=1, le=MAX_MAX_STEPS)]


class SettingsPatch(FrozenModel):
    """Body of ``PATCH /v1/settings``: the ``version`` read, plus at least one change."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Annotated[int, Field(ge=0)]
    run_budget_usd: UsdAmount | None = None
    max_steps: StepCount | None = None

    @model_validator(mode="after")
    def _has_a_change(self) -> Self:
        if self.run_budget_usd is None and self.max_steps is None:
            raise ValueError("give run_budget_usd or max_steps")
        return self


class WorkspaceSettingsView(FrozenModel):
    """Run limits; ``version`` 0 means defaults that were never saved."""

    run_budget_usd: UsdAmount
    max_steps: int
    version: int


class SettingsResponse(FrozenModel):
    keys: ProviderKeys
    settings: WorkspaceSettingsView
