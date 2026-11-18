"""Research module: snapshots, sourced items and the competitor KB. Use only what is exported here.

Snapshots are immutable once closed; competitors are deduped per workspace by their
normalized domain. The module never calls a model: callers pass embeddings in.
"""

from metis.modules.research.controller import router
from metis.modules.research.dto import (
    EMBEDDING_DIMENSIONS,
    Competitor,
    KbMatch,
    KbMatchKind,
    LinkedCompetitor,
    NewCompetitor,
    NewResearchItem,
    ResearchItem,
    ResearchItemKind,
    ResearchSnapshot,
    ResearchView,
)
from metis.modules.research.service.competitors import kb_lookup, upsert_competitor
from metis.modules.research.service.snapshots import (
    add_item,
    close_snapshot,
    get_snapshot,
    latest_snapshot,
    link_competitor,
    open_snapshot,
)

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "Competitor",
    "KbMatch",
    "KbMatchKind",
    "LinkedCompetitor",
    "NewCompetitor",
    "NewResearchItem",
    "ResearchItem",
    "ResearchItemKind",
    "ResearchSnapshot",
    "ResearchView",
    "add_item",
    "close_snapshot",
    "get_snapshot",
    "kb_lookup",
    "latest_snapshot",
    "link_competitor",
    "open_snapshot",
    "router",
    "upsert_competitor",
]
