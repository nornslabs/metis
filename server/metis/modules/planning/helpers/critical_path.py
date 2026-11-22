"""The critical path of a plan: the dependency chain with the most estimate points."""

from __future__ import annotations

from collections import deque
from uuid import UUID

from metis.modules.planning.dto import CriticalPath, Phase


def critical_path(phases: tuple[Phase, ...]) -> CriticalPath:
    """The chain of dependent tasks with the largest sum of estimates, in dependency order.

    Ties go to the task that comes first in the plan (phase, then position), so the result is
    stable. Without dependencies the path is the single largest task. Tasks caught in a
    dependency loop (a stored plan has none) are ignored.
    """
    tasks = [task for phase in phases for task in phase.tasks]
    order = {task.id: index for index, task in enumerate(tasks)}
    by_id = {task.id: task for task in tasks}
    waiting = {task.id: len(task.blocked_by) for task in tasks}
    dependents: dict[UUID, list[UUID]] = {task.id: [] for task in tasks}
    for task in tasks:
        for blocker in task.blocked_by:
            dependents[blocker].append(task.id)

    points: dict[UUID, int] = {}
    previous: dict[UUID, UUID | None] = {}
    queue = deque(task.id for task in tasks if waiting[task.id] == 0)
    while queue:
        current = queue.popleft()
        task = by_id[current]
        best = min(
            (b for b in task.blocked_by if b in points),
            key=lambda b: (-points[b], order[b]),
            default=None,
        )
        points[current] = task.estimate + (0 if best is None else points[best])
        previous[current] = best
        for follower in sorted(dependents[current], key=order.__getitem__):
            waiting[follower] -= 1
            if waiting[follower] == 0:
                queue.append(follower)

    if not points:
        return CriticalPath(task_ids=(), points=0)
    end = min(points, key=lambda t: (-points[t], order[t]))
    chain: list[UUID] = []
    node: UUID | None = end
    while node is not None:
        chain.append(node)
        node = previous[node]
    return CriticalPath(task_ids=tuple(reversed(chain)), points=points[end])
