"""Spec DTOs: the fixed template, versions, diffs and the HTTP bodies."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated
from uuid import UUID

from pydantic import BeforeValidator, ConfigDict, Field

from metis.helpers.dto import FrozenModel
from metis.helpers.text import strip
from metis.modules.ideas.dto.spec_hld import SpecHld

MAX_SPEC_LENGTH = 50_000
NONE_TEXT = "None."


class SpecSection(StrEnum):
    """The template's sections, in the order a spec is written."""

    PROBLEM = "problem"
    TARGET_USERS = "target_users"
    SOLUTION = "solution"
    KEY_FEATURES = "key_features"
    NON_GOALS = "non_goals"
    COMPETITIVE_EDGE = "competitive_edge"
    SUCCESS_METRICS = "success_metrics"
    RISKS = "risks"
    OPEN_QUESTIONS = "open_questions"


SECTION_HEADINGS: MappingProxyType[SpecSection, str] = MappingProxyType(
    {
        SpecSection.PROBLEM: "Problem",
        SpecSection.TARGET_USERS: "Target users",
        SpecSection.SOLUTION: "Solution",
        SpecSection.KEY_FEATURES: "Key features (MVP and later)",
        SpecSection.NON_GOALS: "Non-goals",
        SpecSection.COMPETITIVE_EDGE: "Competitive edge",
        SpecSection.SUCCESS_METRICS: "Success metrics",
        SpecSection.RISKS: "Risks",
        SpecSection.OPEN_QUESTIONS: "Open questions",
    }
)


class SpecSource(StrEnum):
    """Who wrote a version."""

    AGENT = "agent"
    USER = "user"


class DiffStatus(StrEnum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    ADDED = "added"
    REMOVED = "removed"


SpecText = Annotated[str, BeforeValidator(strip), Field(min_length=1, max_length=MAX_SPEC_LENGTH)]


class NewSpecVersion(FrozenModel):
    """A version to save. ``sections`` is parsed from ``content_md`` when left out."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    content_md: str
    source: SpecSource
    sections: dict[str, str] | None = None
    created_by: UUID | None = None
    run_id: UUID | None = None


class SpecVersion(FrozenModel):
    """One version of an idea's spec."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: UUID
    idea_id: UUID
    number: int
    source: SpecSource
    content_md: str
    sections: dict[str, str]
    run_id: UUID | None
    created_by: UUID | None
    created_at: datetime


class SpecVersionSummary(FrozenModel):
    """A version without its text, for the version list."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: UUID
    number: int
    source: SpecSource
    created_by: UUID | None
    created_at: datetime


class SpecVersionList(FrozenModel):
    items: list[SpecVersionSummary]


class SpecOverview(FrozenModel):
    """The latest version and the confirmed one (each ``None`` while there is none), and the
    newest HLD (``None`` for a non-software idea or before one was written)."""

    latest: SpecVersion | None
    confirmed: SpecVersion | None
    hld: SpecHld | None = None


class SectionDiff(FrozenModel):
    section: str
    status: DiffStatus
    a_text: str | None
    b_text: str | None


class SpecDiff(FrozenModel):
    """Section-by-section difference between two versions of one spec."""

    a: int
    b: int
    sections: list[SectionDiff]


class EditSpecBody(FrozenModel):
    """Body of ``POST /v1/ideas/{id}/spec/versions``: the new text and its base version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_number: int = Field(ge=1)
    content_md: SpecText


class ConfirmSpecBody(FrozenModel):
    """Body of ``POST /v1/ideas/{id}/spec/confirm``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    number: int = Field(ge=1)


class SpecConfirmed(FrozenModel):
    """Result of a confirmation: the version, and the run it resumed (``None`` when none waited)."""

    confirmed: SpecVersion
    run_id: UUID | None
