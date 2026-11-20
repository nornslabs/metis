"""SQLAlchemy models for the ``scoring`` schema (migrations ``0017_scoring``, ``0018_suggestions``).

Importing this package registers every table on ``Base.metadata``.
"""

from __future__ import annotations

from metis.modules.scoring.models.rubric import RubricVersionRow
from metis.modules.scoring.models.scores import ScoreParamRow, ScoreRunRow
from metis.modules.scoring.models.suggestions import SuggestionRow

__all__ = ["RubricVersionRow", "ScoreParamRow", "ScoreRunRow", "SuggestionRow"]
