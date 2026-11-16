"""The run status transition table: the status a run may move to from each status."""

from __future__ import annotations

from types import MappingProxyType

from metis.core.errors import IllegalRunTransition
from metis.modules.ideas.dto import RunStatus

TERMINAL_STATUSES = frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED})

ALLOWED_RUN_TRANSITIONS: MappingProxyType[RunStatus, frozenset[RunStatus]] = MappingProxyType(
    {
        RunStatus.QUEUED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
        RunStatus.RUNNING: frozenset(
            {RunStatus.AWAITING_USER, RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
        ),
        RunStatus.AWAITING_USER: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED}),
        RunStatus.SUCCEEDED: frozenset(),
        RunStatus.FAILED: frozenset(),
        RunStatus.CANCELLED: frozenset(),
    }
)


def check_run_transition(current: RunStatus, target: RunStatus) -> None:
    """Raise ``IllegalRunTransition`` unless ``current`` may move to ``target``."""
    if target not in ALLOWED_RUN_TRANSITIONS[current]:
        raise IllegalRunTransition(f"A run that is {current.value} cannot become {target.value}")
