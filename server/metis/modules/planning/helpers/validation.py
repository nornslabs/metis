"""The rules a plan must meet, as pure checks. Failures raise ``InvalidPlanError`` (422)."""

from __future__ import annotations

from collections.abc import Collection, Hashable, Iterable, Mapping
from typing import NoReturn

from metis.core.errors import InvalidPlanError
from metis.modules.planning.dto import (
    ESTIMATES,
    MAX_DEPS,
    MAX_ESTIMATE,
    MAX_PHASES,
    MAX_TASKS,
    InvalidPlanReason,
    PlanInput,
)
from metis.modules.planning.helpers.graph import nodes_on_cycles


def refuse(reason: InvalidPlanReason, message: str, tasks: Iterable[object] = ()) -> NoReturn:
    """Raise the 422 for a broken rule; ``tasks`` names the keys or ids involved."""
    raise InvalidPlanError(message, meta={"reason": reason.value, "tasks": [str(t) for t in tasks]})


def check_estimate(task: object, estimate: int) -> None:
    """The estimate must be 1, 2, 3, 5 or 8; bigger work is split."""
    if estimate in ESTIMATES and not isinstance(estimate, bool):
        return
    hint = " Split work above 8 into smaller tasks." if estimate > MAX_ESTIMATE else ""
    refuse(
        InvalidPlanReason.BAD_ESTIMATE,
        f"Task {task} has estimate {estimate}; use one of {', '.join(map(str, ESTIMATES))}.{hint}",
        [task],
    )


def check_plan_input(plan: PlanInput) -> None:
    """Every rule for a plan about to be saved; nothing is stored before this passes."""
    _check_counts(plan)
    keys = _unique_keys(plan)
    for task in plan.tasks:
        if not 0 <= task.phase < len(plan.phases):
            refuse(
                InvalidPlanReason.UNKNOWN_PHASE,
                f"Task {task.key} is in phase {task.phase}, which does not exist.",
                [task.key],
            )
        check_estimate(task.key, task.estimate)
    parents = {t.key: t.parent_key for t in plan.tasks if t.parent_key is not None}
    deps = [(d.blocked_by_key, d.task_key) for d in plan.deps]
    _check_links(keys, parents, deps)


def check_stored_graph[K: Hashable](
    tasks: Collection[K], parents: Mapping[K, K], deps: list[tuple[K, K]]
) -> None:
    """The graph rules again for a stored plan (before it is marked ready)."""
    if not tasks:
        refuse(InvalidPlanReason.NO_TASKS, "A plan needs at least one task.")
    _check_cycles(tasks, parents, deps)


def _check_counts(plan: PlanInput) -> None:
    if not plan.phases:
        refuse(InvalidPlanReason.NO_PHASES, "A plan needs at least one phase.")
    if not plan.tasks:
        refuse(InvalidPlanReason.NO_TASKS, "A plan needs at least one task.")
    limits = (
        ("phases", len(plan.phases), MAX_PHASES),
        ("tasks", len(plan.tasks), MAX_TASKS),
        ("dependencies", len(plan.deps), MAX_DEPS),
    )
    for name, count, limit in limits:
        if count > limit:
            refuse(
                InvalidPlanReason.LIMIT_EXCEEDED,
                f"A plan has at most {limit} {name}; this one has {count}.",
            )


def _unique_keys(plan: PlanInput) -> set[str]:
    keys: set[str] = set()
    for task in plan.tasks:
        if task.key in keys:
            refuse(
                InvalidPlanReason.DUPLICATE_KEY, f"Task key {task.key} is used twice.", [task.key]
            )
        keys.add(task.key)
    return keys


def _check_links(keys: set[str], parents: Mapping[str, str], deps: list[tuple[str, str]]) -> None:
    for child, parent in parents.items():
        if parent not in keys:
            refuse(
                InvalidPlanReason.UNKNOWN_TASK,
                f"Task {child} has parent {parent}, which is not in the plan.",
                [child, parent],
            )
    seen: set[tuple[str, str]] = set()
    for blocker, task in deps:
        for key in (task, blocker):
            if key not in keys:
                refuse(
                    InvalidPlanReason.UNKNOWN_TASK,
                    f"A dependency names task {key}, which is not in the plan.",
                    [key],
                )
        if task == blocker:
            refuse(InvalidPlanReason.SELF_DEPENDENCY, f"Task {task} depends on itself.", [task])
        if (blocker, task) in seen:
            refuse(
                InvalidPlanReason.DUPLICATE_DEPENDENCY,
                f"Task {task} depends on {blocker} twice.",
                [task, blocker],
            )
        seen.add((blocker, task))
    _check_cycles(sorted(keys), parents, deps)


def _check_cycles[K: Hashable](
    tasks: Iterable[K], parents: Mapping[K, K], deps: list[tuple[K, K]]
) -> None:
    ordered = list(tasks)
    looped = nodes_on_cycles(ordered, deps)
    if looped:
        refuse(
            InvalidPlanReason.DEPENDENCY_CYCLE,
            "These tasks wait on each other in a loop: " + ", ".join(map(str, looped)) + ".",
            looped,
        )
    nested = nodes_on_cycles(ordered, [(parent, child) for child, parent in parents.items()])
    if nested:
        refuse(
            InvalidPlanReason.PARENT_CYCLE,
            "These tasks are each other's parents: " + ", ".join(map(str, nested)) + ".",
            nested,
        )
