"""Research business rules, one file per domain.

Call them domain-qualified, e.g. ``service.snapshots.open_snapshot``.
"""

from __future__ import annotations

from metis.modules.research.service import competitors, snapshots
from metis.modules.research.service.refresh import start_market_recheck, start_rescore

__all__ = ["competitors", "snapshots", "start_market_recheck", "start_rescore"]
