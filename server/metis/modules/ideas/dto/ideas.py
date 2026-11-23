"""Idea DTOs: stages, validated inputs (also the HTTP bodies) and the idea record."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import BeforeValidator, ConfigDict, Field, model_validator

from metis.helpers.dto import FrozenModel
from metis.helpers.text import strip

MIN_TITLE_LENGTH = 3
MAX_TITLE_LENGTH = 120
MIN_RAW_TEXT_LENGTH = 10
MAX_RAW_TEXT_LENGTH = 10_000
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
MAX_SEARCH_LENGTH = 100


class Stage(StrEnum):
    """Where an idea is in the flow. Moves go through ``helpers.transitions``."""

    INTAKE = "intake"
    INTERVIEWING = "interviewing"
    RESEARCHING = "researching"
    SCORING = "scoring"
    ADVISING = "advising"
    SPEC_DRAFT = "spec_draft"
    SPEC_CONFIRMED = "spec_confirmed"
    PLANNING = "planning"
    EXPORTED = "exported"


class IdeaFilter(StrEnum):
    """Which ideas ``GET /v1/ideas`` lists: all, those before ``spec_confirmed``, or scored."""

    ALL = "all"
    IN_PROGRESS = "in_progress"
    SCORED = "scored"


# Stages the ``in_progress`` filter lists: every stage before the spec is confirmed.
IN_PROGRESS_STAGES = (
    Stage.INTAKE,
    Stage.INTERVIEWING,
    Stage.RESEARCHING,
    Stage.SCORING,
    Stage.ADVISING,
    Stage.SPEC_DRAFT,
)


class IdeaKind(StrEnum):
    SOFTWARE = "software"
    OTHER = "other"


Title = Annotated[
    str,
    BeforeValidator(strip),
    Field(min_length=MIN_TITLE_LENGTH, max_length=MAX_TITLE_LENGTH),
]
RawText = Annotated[
    str,
    BeforeValidator(strip),
    Field(min_length=MIN_RAW_TEXT_LENGTH, max_length=MAX_RAW_TEXT_LENGTH),
]


class NewIdea(FrozenModel):
    """Body of ``POST /v1/ideas``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: Title
    raw_text: RawText
    kind: IdeaKind | None = None


class IdeaPatch(FrozenModel):
    """Body of ``PATCH /v1/ideas/{id}``: the ``version`` read, plus at least one change.

    ``kind`` may be sent as ``null`` to clear it, so "not sent" is told apart by
    ``model_fields_set``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Annotated[int, Field(ge=1)]
    title: Title | None = None
    raw_text: RawText | None = None
    kind: IdeaKind | None = None

    @model_validator(mode="after")
    def _has_a_change(self) -> Self:
        if not self.changes:
            raise ValueError("give title, raw_text or kind")
        return self

    @property
    def changes(self) -> dict[str, object]:
        """The fields to write: those sent, with ``title`` / ``raw_text`` never ``None``."""
        sent = self.model_fields_set - {"version"}
        changes = {name: getattr(self, name) for name in sent}
        return {k: v for k, v in changes.items() if v is not None or k == "kind"}


class Idea(FrozenModel):
    """An idea as services and responses carry it (``archived_at`` stays internal)."""

    id: UUID
    workspace_id: UUID
    created_by: UUID
    title: str
    raw_text: str
    kind: IdeaKind | None
    stage: Stage
    current_score: int | None
    version: int
    created_at: datetime
    updated_at: datetime


class IdeaPage(FrozenModel):
    """One page of ideas, latest activity first; ``next_cursor`` is ``None`` on the last page."""

    items: list[Idea]
    next_cursor: str | None
