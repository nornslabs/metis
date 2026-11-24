"""Competitor KB DTOs: a new competitor, a stored one, and KB lookup queries and matches."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Annotated

from pydantic import Field

from metis.helpers.dto import FrozenModel
from metis.modules.research.dto._fields import LongText, Pricing, ShortText, WebUrl

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

EMBEDDING_DIMENSIONS = 1536
DEFAULT_KB_MATCHES = 5
MAX_KB_MATCHES = 20

Embedding = Annotated[
    tuple[float, ...], Field(min_length=EMBEDDING_DIMENSIONS, max_length=EMBEDDING_DIMENSIONS)
]


class NewCompetitor(FrozenModel):
    """A competitor to add to (or refresh in) the KB. ``embedding`` is optional."""

    name: ShortText
    url: WebUrl
    description: LongText | None = None
    pricing: Pricing | None = None
    embedding: Embedding | None = None


class Competitor(FrozenModel):
    """A KB competitor. Its embedding is never returned."""

    id: UUID
    name: str
    url: str
    domain: str
    description: str | None
    pricing: str | None
    created_at: datetime
    updated_at: datetime


class KbMatchKind(StrEnum):
    """How a KB lookup found a competitor."""

    EMBEDDING = "embedding"
    NAME = "name"


class KbQuery(FrozenModel):
    """A KB lookup: a name or domain query, and the query's embedding when there is one."""

    query: ShortText
    k: Annotated[int, Field(ge=1, le=MAX_KB_MATCHES)] = DEFAULT_KB_MATCHES
    query_embedding: Embedding | None = None


class KbMatch(FrozenModel):
    """A KB lookup hit. ``score`` is the cosine similarity for embedding matches, else ``None``."""

    competitor: Competitor
    score: float | None
    matched_by: KbMatchKind
