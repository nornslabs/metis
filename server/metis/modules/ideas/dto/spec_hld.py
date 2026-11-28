"""The HLD of a software idea: what the Architect writes next to spec v1 (a blueprint only)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BeforeValidator, ConfigDict, Field

from metis.helpers.dto import FrozenModel
from metis.helpers.text import strip

MAX_HLD_LENGTH = 30_000
MAX_BUILD_LANGUAGE_LENGTH = 100

HldText = Annotated[str, BeforeValidator(strip), Field(min_length=1, max_length=MAX_HLD_LENGTH)]
BuildLanguage = Annotated[
    str, BeforeValidator(strip), Field(min_length=1, max_length=MAX_BUILD_LANGUAGE_LENGTH)
]


class NewSpecHld(FrozenModel):
    """An HLD to save for spec version ``spec_version_number``, whose text hashes to
    ``spec_hash``."""

    spec_version_number: int = Field(ge=1)
    spec_hash: str = Field(min_length=1)
    build_language: BuildLanguage
    content_md: HldText


class SpecHld(FrozenModel):
    """The HLD written for one spec version. ``stale`` is true when the idea's latest spec text
    differs from the text this HLD was written for (it is not stored)."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: UUID
    idea_id: UUID
    spec_version_number: int
    build_language: str
    content_md: str
    stale: bool = False
    created_at: datetime
