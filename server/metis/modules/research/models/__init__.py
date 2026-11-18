"""SQLAlchemy models for the ``research`` schema (migration ``0016_research``).

Importing this package registers every table on ``Base.metadata``.
"""

from __future__ import annotations

from metis.modules.research.models.competitors import CompetitorRow
from metis.modules.research.models.snapshots import IdeaCompetitorRow, ItemRow, SnapshotRow

__all__ = ["CompetitorRow", "IdeaCompetitorRow", "ItemRow", "SnapshotRow"]
