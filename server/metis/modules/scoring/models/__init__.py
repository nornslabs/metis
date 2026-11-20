"""SQLAlchemy models for the ``scoring`` schema (migration ``0017_scoring``).

Importing this package registers every table on ``Base.metadata``.
"""

from __future__ import annotations

from metis.modules.scoring.models.rubric import RubricVersionRow
from metis.modules.scoring.models.scores import ScoreParamRow, ScoreRunRow

__all__ = ["RubricVersionRow", "ScoreParamRow", "ScoreRunRow"]
