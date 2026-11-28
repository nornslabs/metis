"""What an export to Linear will create, shown to the user before they approve it.

``build_export_preview`` is pure: it takes the idea's title, the stored plan, the Metis ids that
already have a Linear counterpart (``external_refs``) and, when known, the labels Linear
already has. The result is small and JSON-safe, so it goes into the approval interrupt (and so
the checkpoint). Nothing here calls Linear.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Literal
from uuid import UUID

from metis.agent.tools.export_issue import brief_room
from metis.agent.tools.export_project import (
    MAX_PROJECT_NAME_CHARS,
    cut_at_word,
    hld_title,
    suggest_project_names,
)
from metis.agent.tools.issue_brief import fit_brief
from metis.helpers.dto import FrozenModel
from metis.modules.planning import Plan, Task

Action = Literal["create", "update"]


class ExportTeam(FrozenModel):
    """The Linear team the export goes to."""

    id: str
    name: str


class PreviewProject(FrozenModel):
    """``name`` is the name the project gets (the saved one, else the first suggestion);
    ``suggestions`` are the names the user can pick instead (empty in older records)."""

    name: str
    action: Action
    suggestions: tuple[str, ...] = ()


class PreviewHld(FrozenModel):
    """The HLD document the export saves in Linear (only for an idea that has an HLD)."""

    title: str
    action: Action


class PreviewMilestone(FrozenModel):
    name: str
    action: Action


class PreviewMilestones(FrozenModel):
    total: int
    create: int
    update: int
    items: tuple[PreviewMilestone, ...]


class PreviewIssue(FrozenModel):
    """One issue as Linear will show it (before the footer): its title and the brief, fitted the
    same way the export fits it."""

    title: str
    description: str
    component: str | None = None


class PreviewIssues(FrozenModel):
    """``items`` is empty in records saved before issue briefs existed."""

    total: int
    create: int
    update: int
    items: tuple[PreviewIssue, ...] = ()


class PreviewLabel(FrozenModel):
    """``exists`` is ``None`` when Linear's labels could not be checked."""

    name: str
    exists: bool | None


class PreviewLabels(FrozenModel):
    total: int
    items: tuple[PreviewLabel, ...]


class ExportPreview(FrozenModel):
    """The whole preview: what will be created or updated, and where. ``plan_version`` is the
    plan it was built from, so the export can tell whether the plan changed after approval."""

    team: ExportTeam
    plan_version: int
    project: PreviewProject
    hld: PreviewHld | None = None
    milestones: PreviewMilestones
    issues: PreviewIssues
    blocked_by_links: int
    labels: PreviewLabels

    def summary_line(self) -> str:
        """One line for the approval record, e.g. ``Project "X": 3 milestones, 9 issues``."""
        return (
            f'{self.project.action.capitalize()} project "{self.project.name}" in team '
            f"{self.team.name}: {self.milestones.total} milestones, {self.issues.total} issues, "
            f"{self.blocked_by_links} blocked-by links"
        )


def build_export_preview(
    *,
    team: ExportTeam,
    idea_title: str,
    saved_project_name: str | None = None,
    spec_text: str = "",
    plan: Plan,
    project_exists: bool,
    phase_refs: Collection[UUID],
    task_refs: Collection[UUID],
    linear_labels: Collection[str] | None,
    hld_exists: bool | None = None,
) -> ExportPreview:
    """The preview for ``plan``. ``phase_refs`` and ``task_refs`` are the local ids that
    already have a Linear item; ``linear_labels`` is ``None`` when it could not be read.
    ``hld_exists`` is ``None`` when the idea has no HLD, else whether its Linear document exists."""
    suggestions = suggest_project_names(
        saved=saved_project_name, idea_title=idea_title, spec_text=spec_text
    )
    milestones = tuple(
        PreviewMilestone(name=phase.name, action=_action(phase.id in phase_refs))
        for phase in plan.phases
    )
    tasks = [task for phase in plan.phases for task in phase.tasks]
    updated_issues = sum(1 for task in tasks if task.id in task_refs)
    updated_milestones = sum(1 for m in milestones if m.action == "update")
    project_name = (
        suggestions[0] if suggestions else cut_at_word(idea_title, MAX_PROJECT_NAME_CHARS)
    )
    return ExportPreview(
        team=team,
        plan_version=plan.version,
        project=PreviewProject(
            name=project_name,
            action=_action(project_exists),
            suggestions=suggestions,
        ),
        hld=None
        if hld_exists is None
        else PreviewHld(title=hld_title(project_name), action=_action(hld_exists)),
        milestones=PreviewMilestones(
            total=len(milestones),
            create=len(milestones) - updated_milestones,
            update=updated_milestones,
            items=milestones,
        ),
        issues=PreviewIssues(
            total=len(tasks),
            create=len(tasks) - updated_issues,
            update=updated_issues,
            items=tuple(
                PreviewIssue(
                    title=task.title,
                    description=fit_brief(
                        task.description,
                        brief_room(design_chars=None if hld_exists is None else 0),
                    ),
                    component=task.component if hld_exists is not None else None,
                )
                for task in tasks
            ),
        ),
        blocked_by_links=sum(len(task.blocked_by) for task in tasks),
        labels=_labels(tasks, linear_labels),
    )


def with_project_name(preview: ExportPreview, name: str) -> ExportPreview:
    """``preview`` with the name the user approved (the suggestions stay as shown)."""
    update: dict[str, object] = {"project": preview.project.model_copy(update={"name": name})}
    if preview.hld is not None:
        update["hld"] = preview.hld.model_copy(update={"title": hld_title(name)})
    return preview.model_copy(update=update)


def _action(exists: bool) -> Action:
    return "update" if exists else "create"


def _labels(tasks: Collection[Task], linear_labels: Collection[str] | None) -> PreviewLabels:
    used = sorted({label for task in tasks for label in task.labels})
    known = None if linear_labels is None else {name.casefold() for name in linear_labels}
    items = tuple(
        PreviewLabel(name=name, exists=None if known is None else name.casefold() in known)
        for name in used
    )
    return PreviewLabels(total=len(items), items=items)
