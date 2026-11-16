"""SQLAlchemy models for the ``ideas`` schema (migrations ``0010_ideas``, ``0011_llm_usage``).

Importing this package registers every table on ``Base.metadata``.
"""

from __future__ import annotations

from metis.modules.ideas.models.ideas import IdeaRow
from metis.modules.ideas.models.llm_usage import LlmUsageRow

__all__ = ["IdeaRow", "LlmUsageRow"]
