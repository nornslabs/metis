"""Research business rules, one file per domain.

Call them domain-qualified, e.g. ``service.snapshots.open_snapshot``.
"""

from __future__ import annotations

from metis.modules.research.service import competitors, snapshots

__all__ = ["competitors", "snapshots"]
