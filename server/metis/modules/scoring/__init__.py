"""Scoring module: the fixed rubric and immutable score runs. Use only what is exported here.

A score run stores six per-parameter results; the total and band are computed by
``record_score``, never supplied. The module never calls a model: the Scorer submits marks.
"""

from metis.modules.scoring.controller import router
from metis.modules.scoring.dto import (
    NO_EVIDENCE_MAX_CONFIDENCE,
    NewEvidence,
    NewParamScore,
    ParamDiff,
    Rubric,
    ScoreBand,
    ScoreDiff,
    ScoreHistory,
    ScoreParam,
    ScoreParamResult,
    ScoreRun,
    ScoreRunSummary,
    ScoreTrigger,
)
from metis.modules.scoring.service.rubric import get_rubric
from metis.modules.scoring.service.scores import (
    diff,
    get_score_run,
    latest_score,
    record_score,
    score_history,
)

__all__ = [
    "NO_EVIDENCE_MAX_CONFIDENCE",
    "NewEvidence",
    "NewParamScore",
    "ParamDiff",
    "Rubric",
    "ScoreBand",
    "ScoreDiff",
    "ScoreHistory",
    "ScoreParam",
    "ScoreParamResult",
    "ScoreRun",
    "ScoreRunSummary",
    "ScoreTrigger",
    "diff",
    "get_rubric",
    "get_score_run",
    "latest_score",
    "record_score",
    "router",
    "score_history",
]
