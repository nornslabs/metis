"""The order and the text of the Linear issues (SHIP-254): pure functions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from metis.agent.tools.export_issue import (
    issue_description,
    issue_title,
    labels_for,
    labels_to_create,
    ordered_tasks,
)
from metis.agent.tools.export_project import MAX_DESCRIPTION_CHARS, MAX_NAME_CHARS
from metis.modules.planning import CriticalPath, Phase, Plan, PlanStatus, Task

URL = "https://metis.test/ideas/1"


def _task(
    position: int,
    *,
    blocked_by: tuple[UUID, ...] = (),
    parent: UUID | None = None,
    labels: tuple[str, ...] = (),
) -> Task:
    return Task(
        id=uuid4(),
        position=position,
        title=f"Task {position}",
        description="",
        estimate=1,
        labels=labels,
        parent_task_id=parent,
        blocked_by=blocked_by,
    )


def _plan(*phases: tuple[Task, ...]) -> Plan:
    now = datetime.now(tz=UTC)
    return Plan(
        id=uuid4(),
        idea_id=uuid4(),
        spec_version_id=uuid4(),
        status=PlanStatus.DRAFT,
        version=1,
        ready_at=None,
        created_at=now,
        updated_at=now,
        phases=tuple(
            Phase(id=uuid4(), position=i, name=f"P{i}", goal="g", exit_criteria="e", tasks=tasks)
            for i, tasks in enumerate(phases)
        ),
        critical_path=CriticalPath(task_ids=(), points=0),
    )


def test_tasks_keep_plan_order_when_nothing_depends_on_anything() -> None:
    a, b, c = _task(0), _task(1), _task(2)

    assert ordered_tasks(_plan((a, b), (c,))) == [a, b, c]


def test_a_blocker_comes_before_the_task_it_blocks_even_from_a_later_phase() -> None:
    late = _task(0)
    early = _task(0, blocked_by=(late.id,))

    assert ordered_tasks(_plan((early,), (late,))) == [late, early]


def test_a_parent_comes_before_its_sub_tasks() -> None:
    parent = _task(1)
    child = _task(0, parent=parent.id)

    assert ordered_tasks(_plan((child, parent))) == [parent, child]


def test_a_cycle_loses_no_task() -> None:
    a = _task(0)
    b = _task(1, blocked_by=(a.id,))
    cyclic = a.model_copy(update={"blocked_by": (b.id,)})

    assert {t.id for t in ordered_tasks(_plan((cyclic, b)))} == {a.id, b.id}


def test_an_issue_description_is_the_task_text_then_a_metis_footer() -> None:
    text = issue_description("Do it.\n\n- step", URL)

    assert text.startswith("Do it.\n\n- step")
    assert text.endswith(f"Created by [Metis]({URL})")


def test_an_empty_task_text_leaves_only_the_footer() -> None:
    assert issue_description("  ", URL) == f"---\nCreated by [Metis]({URL})"


def test_a_long_description_is_cut_but_keeps_the_footer_within_the_limit() -> None:
    text = issue_description("x" * 9000, URL)

    assert len(text) <= MAX_DESCRIPTION_CHARS
    assert text.endswith(f"Created by [Metis]({URL})")


def test_a_long_title_is_cut() -> None:
    assert len(issue_title("t" * 1000)) == MAX_NAME_CHARS


def test_only_labels_missing_in_linear_are_created_ignoring_case() -> None:
    used = {"backend", "Frontend", "frontend", "API"}

    assert labels_to_create(used, ["Backend", "bug"]) == ["API", "Frontend"]


def test_a_task_carries_only_labels_that_exist_spelled_as_linear_has_them() -> None:
    task = _task(0, labels=("backend", "Frontend", "nope", "BACKEND"))

    assert labels_for(task, {"backend": "Backend", "frontend": "Frontend"}) == [
        "Backend",
        "Frontend",
    ]
