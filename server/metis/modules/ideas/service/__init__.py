"""Ideas business rules, one file per domain.

Call them domain-qualified, e.g. ``service.ideas.create_idea``.
"""

from __future__ import annotations

from metis.modules.ideas.service import ideas

__all__ = ["ideas"]
