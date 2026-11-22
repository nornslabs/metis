"""Planning enums and the fixed limits of a plan."""

from __future__ import annotations

from enum import StrEnum

ESTIMATES: tuple[int, ...] = (1, 2, 3, 5, 8)
MAX_ESTIMATE = ESTIMATES[-1]
MAX_PHASES = 12
MAX_TASKS = 200
MAX_DEPS = 600
MAX_LABELS = 10
MAX_PHASE_OPS = 50


class PlanStatus(StrEnum):
    """A plan is edited as a ``draft`` and fixed once ``ready``."""

    DRAFT = "draft"
    READY = "ready"


class InvalidPlanReason(StrEnum):
    """Why a plan was refused (``meta.reason`` of ``plan.invalid_plan``)."""

    NO_PHASES = "no_phases"
    NO_TASKS = "no_tasks"
    LIMIT_EXCEEDED = "limit_exceeded"
    DUPLICATE_KEY = "duplicate_key"
    UNKNOWN_PHASE = "unknown_phase"
    UNKNOWN_TASK = "unknown_task"
    BAD_ESTIMATE = "bad_estimate"
    BAD_POSITION = "bad_position"
    BAD_OPERATION = "bad_operation"
    SELF_DEPENDENCY = "self_dependency"
    DUPLICATE_DEPENDENCY = "duplicate_dependency"
    DEPENDENCY_CYCLE = "dependency_cycle"
    PARENT_CYCLE = "parent_cycle"
