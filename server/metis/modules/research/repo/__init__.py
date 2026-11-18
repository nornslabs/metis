"""Postgres access for the research module, one file per table.

Call it domain-qualified: ``repo.snapshots.get(...)``.
"""

from __future__ import annotations

from metis.modules.research.repo import competitors, idea_competitors, items, snapshots

__all__ = ["competitors", "idea_competitors", "items", "snapshots"]
