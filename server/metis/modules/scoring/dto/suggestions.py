"""Suggestion DTOs: what the Advisor saves, and the stored suggestions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import Field, StringConstraints, model_validator

from metis.helpers.dto import FrozenModel
from metis.modules.scoring.dto._fields import Reason
from metis.modules.scoring.dto.enums import ScoreParam, SuggestionKind, SuggestionStatus
from metis.modules.scoring.dto.scores import MAX_EVIDENCE_ITEMS, EvidenceItem, NewEvidence

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

MAX_TARGET_PARAMS = 3
MAX_SUGGESTION_TITLE = 200
MAX_EXPECTED_IMPACT = 500

SuggestionTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_SUGGESTION_TITLE)
]
ExpectedImpact = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_EXPECTED_IMPACT)
]


class NewSuggestion(FrozenModel):
    """One suggestion as the Advisor saves it. A suggestion needs at least one source."""

    kind: SuggestionKind
    title: SuggestionTitle
    rationale: Reason
    target_params: tuple[ScoreParam, ...] = Field(min_length=1, max_length=MAX_TARGET_PARAMS)
    expected_impact: ExpectedImpact
    evidence: tuple[NewEvidence, ...] = Field(min_length=1, max_length=MAX_EVIDENCE_ITEMS)

    @model_validator(mode="after")
    def _check_params(self) -> NewSuggestion:
        if len(set(self.target_params)) != len(self.target_params):
            raise ValueError("target_params has a parameter twice")
        return self


class Suggestion(FrozenModel):
    """A stored suggestion."""

    id: UUID
    idea_id: UUID
    score_run_id: UUID
    kind: SuggestionKind
    title: str
    rationale: str
    target_params: tuple[ScoreParam, ...]
    expected_impact: str
    evidence: tuple[EvidenceItem, ...]
    status: SuggestionStatus
    created_at: datetime


class SuggestionList(FrozenModel):
    """An idea's suggestions: newest score run first, then in the order they were saved."""

    items: tuple[Suggestion, ...]


class SuggestionStatusBody(FrozenModel):
    """``PATCH /v1/suggestions/{id}``."""

    status: SuggestionStatus
