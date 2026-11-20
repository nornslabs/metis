"""Postgres access for the scoring module, one file per table.

Call it table-qualified: ``repo.score_runs.get(...)``.
"""

from __future__ import annotations

from metis.modules.scoring.repo import rubric, score_params, score_runs, suggestions

__all__ = ["rubric", "score_params", "score_runs", "suggestions"]
