"""Scoring business rules, one file per domain.

Call them domain-qualified, e.g. ``service.scores.record_score``.
"""

from __future__ import annotations

from metis.modules.scoring.service import rubric, scores, suggestions

__all__ = ["rubric", "scores", "suggestions"]
