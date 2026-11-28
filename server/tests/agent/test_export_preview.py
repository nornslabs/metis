"""The export preview as a pure function: counts, create/update marks and label checks."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from metis.agent.tools.export_issue import brief_room, issue_description
from metis.agent.tools.export_preview import (
    ExportPreview,
    ExportTeam,
    build_export_preview,
    with_project_name,
)
from metis.modules.planning import CriticalPath, Phase, Plan, PlanStatus, Task

TEAM = ExportTeam(id="team-1", name="Product")
NOW = datetime(2026, 11, 24, tzinfo=UTC)


def _task(position: int, labels: tuple[str, ...] = (), blocked_by: tuple[UUID, ...] = ()) -> Task:
    return Task(
        id=uuid4(),
        position=position,
        title=f"Task {position}",
        description="",
        estimate=3,
        labels=labels,
        parent_task_id=None,
        blocked_by=blocked_by,
    )


def _plan(phases: list[list[Task]]) -> Plan:
    return Plan(
        id=uuid4(),
        idea_id=uuid4(),
        spec_version_id=uuid4(),
        status=PlanStatus.DRAFT,
        version=1,
        ready_at=None,
        created_at=NOW,
        updated_at=NOW,
        phases=tuple(
            Phase(
                id=uuid4(),
                position=i,
                name=f"Phase {i}",
                goal="g",
                exit_criteria="e",
                tasks=tuple(tasks),
            )
            for i, tasks in enumerate(phases)
        ),
        critical_path=CriticalPath(task_ids=(), points=0),
    )


def _preview(plan: Plan, **overrides: object):  # type: ignore[no-untyped-def]
    args: dict[str, object] = {
        "team": TEAM,
        "idea_title": "Pocket CRM",
        "plan": plan,
        "project_exists": False,
        "phase_refs": frozenset(),
        "task_refs": frozenset(),
        "linear_labels": None,
    }
    return build_export_preview(**{**args, **overrides})  # type: ignore[arg-type]


def test_every_count_comes_from_the_plan() -> None:
    first = _task(0, ("backend",))
    second = _task(1, ("backend", "ui"), (first.id,))
    third = _task(2, (), (first.id, second.id))
    plan = _plan([[first], [second, third]])

    preview = _preview(plan)

    assert preview.project.name == "Pocket CRM"
    assert (preview.milestones.total, preview.issues.total) == (2, 3)
    assert preview.blocked_by_links == 3
    assert [label.name for label in preview.labels.items] == ["backend", "ui"]


def test_every_issue_carries_its_title_and_its_brief() -> None:
    brief = "## Goal\nG.\n\n## Requirements\n1. R.\n\n## Acceptance criteria\n- A."
    task = _task(0).model_copy(update={"description": brief})

    preview = _preview(_plan([[task]]))

    assert [(i.title, i.description) for i in preview.issues.items] == [(task.title, brief)]


def test_a_record_saved_before_briefs_has_no_issue_items() -> None:
    record = _preview(_plan([[_task(0)]])).model_dump(mode="json")
    record["issues"].pop("items")

    assert ExportPreview.model_validate(record).issues.items == ()


def test_the_preview_fits_a_long_brief_exactly_as_the_export_will() -> None:
    brief = (
        "## Goal\nG.\n\n## Requirements\n1. R.\n\n## Acceptance criteria\n- A.\n\n## Agent notes\n"
        + ("n" * 5_000)
    )
    task = _task(0).model_copy(update={"description": brief})

    shown = _preview(_plan([[task]])).issues.items[0].description
    written = issue_description(brief, "https://metis.test/ideas/1")

    assert written.startswith(shown) and len(shown) <= brief_room()


def test_nothing_exported_before_means_everything_is_created() -> None:
    preview = _preview(_plan([[_task(0)], [_task(1)]]))

    assert (preview.project.action, preview.milestones.update, preview.issues.update) == (
        "create",
        0,
        0,
    )
    assert preview.milestones.create == 2 and preview.issues.create == 2


def test_items_with_a_ref_are_updates_and_the_counts_add_up() -> None:
    first, second, third = _task(0), _task(1), _task(2)
    plan = _plan([[first, second], [third]])

    preview = _preview(
        plan,
        project_exists=True,
        phase_refs={plan.phases[1].id},
        task_refs={first.id, third.id},
    )

    assert preview.project.action == "update"
    assert [m.action for m in preview.milestones.items] == ["create", "update"]
    assert (preview.issues.create, preview.issues.update) == (1, 2)
    assert preview.issues.create + preview.issues.update == preview.issues.total
    assert preview.milestones.create + preview.milestones.update == preview.milestones.total


def test_labels_are_checked_against_linear_ignoring_case() -> None:
    plan = _plan([[_task(0, ("Backend", "ui"))]])

    preview = _preview(plan, linear_labels=["backend", "bug"])

    assert {label.name: label.exists for label in preview.labels.items} == {
        "Backend": True,
        "ui": False,
    }


def test_labels_are_unchecked_when_linears_labels_are_unknown() -> None:
    preview = _preview(_plan([[_task(0, ("ui",))]]), linear_labels=None)

    assert [label.exists for label in preview.labels.items] == [None]


def test_the_summary_line_names_the_team_and_the_counts() -> None:
    preview = _preview(_plan([[_task(0)]]))

    assert preview.summary_line() == (
        'Create project "Pocket CRM" in team Product: 1 milestones, 1 issues, 0 blocked-by links'
    )


def test_the_project_name_is_the_first_suggestion_and_never_over_linears_limit() -> None:
    title = "An AI assistant that helps small restaurant owners plan their weekly menus and orders"
    preview = _preview(_plan([[_task(0)]]), idea_title=title, spec_text="# Menu Pilot")

    assert preview.project.name == preview.project.suggestions[0]
    assert all(len(name) <= 80 for name in preview.project.suggestions)
    assert "Menu Pilot" in preview.project.suggestions


def test_a_saved_project_name_is_kept_for_a_re_export() -> None:
    preview = _preview(_plan([[_task(0)]]), saved_project_name="Menu Pilot", project_exists=True)

    assert preview.project.name == "Menu Pilot"
    assert preview.project.action == "update"


def test_the_approved_name_replaces_the_shown_one_and_keeps_the_suggestions() -> None:
    preview = _preview(_plan([[_task(0)]]))

    approved = with_project_name(preview, "My own name")

    assert approved.project.name == "My own name"
    assert approved.project.suggestions == preview.project.suggestions
    assert preview.project.name != "My own name"
