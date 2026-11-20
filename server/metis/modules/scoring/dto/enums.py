"""The rubric's vocabulary: parameters, bands and what triggered a score."""

from __future__ import annotations

from enum import StrEnum


class ScoreParam(StrEnum):
    """The six fixed rubric parameters, in rubric order."""

    PROBLEM_SEVERITY = "problem_severity"
    UNIQUENESS = "uniqueness"
    MARKET_DEMAND = "market_demand"
    VALUE = "value"
    FEASIBILITY = "feasibility"
    TIMING = "timing"


class ScoreBand(StrEnum):
    """``build`` from 75, ``promising`` 55–74, ``advise`` below 55."""

    BUILD = "build"
    PROMISING = "promising"
    ADVISE = "advise"


class ScoreTrigger(StrEnum):
    """Why a score was made."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    SIGNAL = "signal"


class SuggestionKind(StrEnum):
    """What a suggestion changes."""

    FEATURE = "feature"
    NICHE = "niche"
    PRICING = "pricing"
    PIVOT = "pivot"


class SuggestionStatus(StrEnum):
    """Where a suggestion stands with the user."""

    OPEN = "open"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
