"""The text and the order of the Linear issues the export creates, one per plan task.

Pure functions: tasks go in, an order, titles and Markdown descriptions come out, cut to fixed
limits. Nothing here calls Linear or reads secrets.
"""

from __future__ import annotations

import heapq
from collections.abc import Collection, Mapping
from uuid import UUID

from metis.agent.tools.export_project import MAX_DESCRIPTION_CHARS, MAX_NAME_CHARS, cut
from metis.agent.tools.issue_brief import fit_brief
from metis.modules.planning import Plan, Task

FOOTER_LABEL = "Created by"
# The footer is reserved at this size, so the preview and the export fit a brief to the same
# length (a footer is a short line: the label and one link).
FOOTER_RESERVE_CHARS = 200
BRIEF_SEPARATOR_CHARS = 2


def ordered_tasks(plan: Plan) -> list[Task]:
    """The plan's tasks so that every task comes after its parent and after the tasks that block
    it; ties keep plan order (phase position, then task position).

    A cycle cannot be saved (the plan rules refuse it); if one slipped in, its tasks are added
    last in plan order instead of being lost.
    """
    tasks = [task for phase in plan.phases for task in phase.tasks]
    index = {task.id: i for i, task in enumerate(tasks)}
    waiting_on = {
        task.id: {dep for dep in (*task.blocked_by, task.parent_task_id) if dep in index}
        for task in tasks
    }
    dependants: dict[UUID, list[UUID]] = {}
    for task_id, deps in waiting_on.items():
        for dep in deps:
            dependants.setdefault(dep, []).append(task_id)
    ready = [index[task_id] for task_id, deps in waiting_on.items() if not deps]
    heapq.heapify(ready)
    ordered: list[Task] = []
    while ready:
        task = tasks[heapq.heappop(ready)]
        ordered.append(task)
        for dependant in dependants.get(task.id, ()):
            waiting_on[dependant].discard(task.id)
            if not waiting_on[dependant]:
                heapq.heappush(ready, index[dependant])
    placed = {task.id for task in ordered}
    return [*ordered, *(task for task in tasks if task.id not in placed)]


def issue_title(title: str) -> str:
    return cut(title, MAX_NAME_CHARS)


def brief_room(footer_chars: int = 0) -> int:
    """How many characters the brief gets once the footer and its separator are kept."""
    reserved = max(footer_chars, FOOTER_RESERVE_CHARS) + BRIEF_SEPARATOR_CHARS
    return max(MAX_DESCRIPTION_CHARS - reserved, 0)


def issue_description(description: str, idea_url: str) -> str:
    """The task's issue brief (Agent notes in a collapsible block), then a "Created by Metis"
    footer linking back to the idea. The brief is fitted so the whole stays within Linear's
    limit: Agent notes go first, then Context, and Acceptance criteria are kept whole."""
    footer = f"---\n{FOOTER_LABEL} [Metis]({idea_url})"
    body = fit_brief(description, brief_room(len(footer)))
    return f"{body}\n\n{footer}" if body else footer


def labels_to_create(used: Collection[str], existing: Collection[str]) -> list[str]:
    """The task labels Linear does not have yet (case-insensitive), one spelling each, sorted."""
    known = {name.casefold() for name in existing}
    missing: dict[str, str] = {}
    for name in sorted(used):
        key = name.casefold()
        if key not in known and key not in missing:
            missing[key] = name
    return list(missing.values())


def labels_for(task: Task, usable: Mapping[str, str]) -> list[str]:
    """The task's labels that exist (or were just created) on the team, spelled as Linear has
    them. ``usable`` maps a lower-cased name to Linear's spelling."""
    seen: set[str] = set()
    names: list[str] = []
    for label in task.labels:
        key = label.casefold()
        if key in usable and key not in seen:
            seen.add(key)
            names.append(usable[key])
    return names
