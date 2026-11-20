"""The stage transition table: which stage an idea may move to from each stage."""

from __future__ import annotations

from types import MappingProxyType

from metis.core.errors import IllegalTransition
from metis.modules.ideas.dto import Stage

ALLOWED_TRANSITIONS: MappingProxyType[Stage, frozenset[Stage]] = MappingProxyType(
    {
        Stage.INTAKE: frozenset({Stage.INTERVIEWING}),
        Stage.INTERVIEWING: frozenset({Stage.RESEARCHING}),
        Stage.RESEARCHING: frozenset({Stage.SCORING}),
        Stage.SCORING: frozenset({Stage.ADVISING, Stage.SPEC_DRAFT}),
        # Revise and rescore: the user adds detail, the idea is researched or scored again.
        # Or the user goes on to the spec anyway (or the idea was only promising).
        Stage.ADVISING: frozenset(
            {Stage.INTERVIEWING, Stage.RESEARCHING, Stage.SCORING, Stage.SPEC_DRAFT}
        ),
        Stage.SPEC_DRAFT: frozenset({Stage.SPEC_CONFIRMED}),
        # Back to the draft to edit the spec, or on to the plan.
        Stage.SPEC_CONFIRMED: frozenset({Stage.SPEC_DRAFT, Stage.PLANNING}),
        Stage.PLANNING: frozenset({Stage.EXPORTED}),
        # Rebalance: export again after the plan changed.
        Stage.EXPORTED: frozenset({Stage.PLANNING}),
    }
)


def check_transition(current: Stage, target: Stage) -> None:
    """Raise ``IllegalTransition`` unless ``current`` may move to ``target``."""
    if target not in ALLOWED_TRANSITIONS[current]:
        raise IllegalTransition(f"An idea in {current.value} cannot move to {target.value}")
