"""Research snapshot DTOs: item kinds, new items, stored items and the snapshot views."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from metis.helpers.dto import FrozenModel
from metis.modules.research.dto._fields import Fraction, LongText, Summary, Title, WebUrl

if TYPE_CHECKING:
    from datetime import date, datetime
    from uuid import UUID


class ResearchItemKind(StrEnum):
    """What a research item is. ``competitor`` and ``market_fact`` must cite a URL."""

    COMPETITOR = "competitor"
    MARKET_FACT = "market_fact"
    TREND = "trend"
    RISK = "risk"


SOURCED_KINDS = frozenset({ResearchItemKind.COMPETITOR, ResearchItemKind.MARKET_FACT})


class NewResearchItem(FrozenModel):
    """A finding to add to an open snapshot. The service checks the URL rule by kind."""

    kind: ResearchItemKind
    title: Title
    url: WebUrl | None = None
    published_at: date | None = None
    quote: LongText | None = None
    claim: LongText
    confidence: Fraction


class ResearchItem(FrozenModel):
    """A stored finding."""

    id: UUID
    kind: ResearchItemKind
    title: str
    url: str | None
    published_at: date | None
    quote: str | None
    claim: str
    confidence: float


class ResearchSnapshot(FrozenModel):
    """A research version of an idea; ``closed_at`` is ``None`` while it is still written."""

    id: UUID
    idea_id: UUID
    run_id: UUID
    summary: str | None
    closed_at: datetime | None
    created_at: datetime


class SnapshotClose(FrozenModel):
    """The summary a snapshot is closed with."""

    summary: Summary


class CompetitorLink(FrozenModel):
    """How much a competitor overlaps the snapshot's idea, 0–1."""

    overlap: Fraction


class LinkedCompetitor(FrozenModel):
    """A competitor as found by one snapshot, with its overlap."""

    id: UUID
    name: str
    url: str
    domain: str
    description: str | None
    pricing: str | None
    overlap: float
    updated_at: datetime


class ResearchView(ResearchSnapshot):
    """A snapshot with its items (oldest first) and competitors (most overlap first)."""

    items: tuple[ResearchItem, ...]
    competitors: tuple[LinkedCompetitor, ...]
