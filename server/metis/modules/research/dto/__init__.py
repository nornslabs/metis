"""Research DTOs; every public name is re-exported here."""

from __future__ import annotations

from metis.modules.research.dto.competitors import (
    DEFAULT_KB_MATCHES,
    EMBEDDING_DIMENSIONS,
    MAX_KB_MATCHES,
    Competitor,
    KbMatch,
    KbMatchKind,
    KbQuery,
    NewCompetitor,
)
from metis.modules.research.dto.snapshots import (
    SOURCED_KINDS,
    CompetitorLink,
    LinkedCompetitor,
    NewResearchItem,
    ResearchItem,
    ResearchItemKind,
    ResearchSnapshot,
    ResearchView,
    SnapshotClose,
)

__all__ = [
    "DEFAULT_KB_MATCHES",
    "EMBEDDING_DIMENSIONS",
    "MAX_KB_MATCHES",
    "SOURCED_KINDS",
    "Competitor",
    "CompetitorLink",
    "KbMatch",
    "KbMatchKind",
    "KbQuery",
    "LinkedCompetitor",
    "NewCompetitor",
    "NewResearchItem",
    "ResearchItem",
    "ResearchItemKind",
    "ResearchSnapshot",
    "ResearchView",
    "SnapshotClose",
]
