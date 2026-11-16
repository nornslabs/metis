"""SQLAlchemy models for the ``ideas`` schema (migration ``0010_ideas``).

Importing this package registers every table on ``Base.metadata``.
"""

from __future__ import annotations

from metis.modules.ideas.models.ideas import IdeaRow

__all__ = ["IdeaRow"]
