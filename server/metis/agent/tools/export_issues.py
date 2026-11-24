"""The Linear writes of the export's last steps: the labels, one issue per task, the blocked-by
links.

Labels are made first, then the issues in an order where a task follows its parent and its
blockers, then one ``save_issue`` per task that has blockers (Linear's ``blockedBy`` only adds, so
sending links again is safe). Create or update is decided by ``external_refs`` and each ref is
committed right after its call (see ``export_writes``).

A failed issue or link does not stop the others: the failure is recorded in the tally and what
depends on it is skipped. A failure that says Linear itself is not answering (unreachable, timed
out, rate limited) stops the step, and the error is handed back to the caller after the saved work
is recorded. Linear's argument shapes live in the small adapter functions at the bottom.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain_core.tools import BaseTool

from metis.agent.tools.export_issue import (
    issue_description,
    issue_title,
    labels_for,
    labels_to_create,
    ordered_tasks,
)
from metis.agent.tools.export_linear import CREATE_LABEL, LIST_LABELS, label_args, read_label_names
from metis.agent.tools.export_writes import (
    ExportTally,
    action_of,
    call_tool,
    parse_saved_item,
    publish_progress,
    save_item,
)
from metis.agent.tools.mcp import McpRunContext
from metis.core.errors import UpstreamError
from metis.core.events import RunEventType, publish
from metis.core.logging import get_logger
from metis.helpers.http import FailureReason
from metis.helpers.mcp import failure_reason
from metis.modules import integrations
from metis.modules.integrations import ExternalRef, IntegrationProvider, LocalKind
from metis.modules.planning import Plan, Task

SAVE_ISSUE = "save_issue"
ITEM_ISSUE = "issue"
ITEM_LINK = "link"
ITEM_LINKS = "links"
LINKS_NAME = "Blocked-by links"
NOTICE_LABELS_SKIPPED = "export.labels_skipped"
NOTICE_LABELS_SKIPPED_TEXT = (
    "Some labels could not be created in Linear, so the issues were made without them."
)
REASON_SKIPPED = "skipped"
# A failure of this kind says Linear is not answering, not that one item is wrong: stop.
_STOPPING_REASONS = frozenset(
    {FailureReason.UNREACHABLE, FailureReason.TIMEOUT, FailureReason.RATE_LIMITED}
)
_PROVIDER = IntegrationProvider.LINEAR

logger = get_logger(__name__)


@dataclass(frozen=True)
class IssueSource:
    """What the issues are made from."""

    plan: Plan
    team_id: str
    project_id: str
    milestone_ids: dict[UUID, str]
    idea_url: str
    # Progress already published by the project and milestone steps.
    done: int
    total: int

    @property
    def milestone_of_task(self) -> dict[UUID, str]:
        """The Linear milestone of every task, by task id (its phase's milestone)."""
        return {
            task.id: self.milestone_ids[phase.id]
            for phase in self.plan.phases
            for task in phase.tasks
            if phase.id in self.milestone_ids
        }


async def write_issues_and_links(
    context: McpRunContext,
    tools: dict[str, BaseTool],
    source: IssueSource,
    tally: ExportTally,
) -> UpstreamError | None:
    """Create or update the issues, then add the blocked-by links. Never raises for one bad
    item; returns the error that stopped it when Linear stopped answering."""
    tasks = ordered_tasks(source.plan)
    usable = await _ensure_labels(context, tools, source.team_id, tasks)
    refs = await _task_refs(context, tasks)
    issue_ids: dict[UUID, str] = {}
    milestones = source.milestone_of_task
    done = source.done
    for task in tasks:
        existing = refs.get(task.id)
        saved, failure = await _write_issue(
            context,
            tools,
            source,
            task,
            _IssueInputs(existing, usable, milestones),
            issue_ids,
            tally,
        )
        if failure is not None:
            return failure
        if saved:
            done += 1
            await publish_progress(
                context,
                ITEM_ISSUE,
                issue_title(task.title),
                action_of(existing),
                done,
                source.total,
            )
    return await _write_links(context, tools, source, tasks, issue_ids, tally, done)


@dataclass(frozen=True)
class _IssueInputs:
    existing: ExternalRef | None
    usable_labels: dict[str, str]
    milestones: dict[UUID, str]


async def _write_issue(
    context: McpRunContext,
    tools: dict[str, BaseTool],
    source: IssueSource,
    task: Task,
    inputs: _IssueInputs,
    issue_ids: dict[UUID, str],
    tally: ExportTally,
) -> tuple[bool, UpstreamError | None]:
    """Save one issue. Returns whether it was saved and, when Linear stopped answering, the
    error that ends the step. A failure of this one issue is recorded in the tally."""
    parent_id = issue_ids.get(task.parent_task_id) if task.parent_task_id is not None else None
    if task.parent_task_id is not None and parent_id is None:
        tally.failed.append(_failed(ITEM_ISSUE, task, REASON_SKIPPED))
        return False, None
    arguments = _issue_args(source, task, inputs, parent_id)
    try:
        saved = await save_item(context, tools, SAVE_ISSUE, arguments, LocalKind.TASK, task.id)
    except UpstreamError as exc:
        tally.failed.append(_failed(ITEM_ISSUE, task, failure_reason(exc).value))
        return False, exc if _stops(exc) else None
    issue_ids[task.id] = saved.external_id
    tally.record(action_of(inputs.existing))
    logger.info("export.issue_saved", action=action_of(inputs.existing))
    return True, None


async def _write_links(
    context: McpRunContext,
    tools: dict[str, BaseTool],
    source: IssueSource,
    tasks: list[Task],
    issue_ids: dict[UUID, str],
    tally: ExportTally,
    done: int,
) -> UpstreamError | None:
    """One ``save_issue`` per task with blockers, naming the blockers that have an issue. A
    blocker without an issue is skipped and recorded."""
    sent_before = tally.links
    for task in tasks:
        if not task.blocked_by:
            continue
        blockers = [issue_ids[b] for b in task.blocked_by if b in issue_ids]
        if task.id not in issue_ids or len(blockers) < len(task.blocked_by):
            tally.failed.append(_failed(ITEM_LINK, task, REASON_SKIPPED))
        if task.id not in issue_ids or not blockers:
            continue
        try:
            await call_tool(
                tools, SAVE_ISSUE, _links_args(issue_ids[task.id], blockers), ITEM_LINKS
            )
        except UpstreamError as exc:
            tally.failed.append(_failed(ITEM_LINK, task, failure_reason(exc).value))
            if _stops(exc):
                return exc
            continue
        tally.links += len(blockers)
    sent = tally.links - sent_before
    if sent:
        await publish_progress(context, ITEM_LINKS, LINKS_NAME, "update", done + 1, source.total)
        logger.info("export.links_saved", count=sent)
    return None


async def _ensure_labels(
    context: McpRunContext, tools: dict[str, BaseTool], team_id: str, tasks: list[Task]
) -> dict[str, str]:
    """Make the labels the tasks use exist on the team. Returns the labels issues may carry,
    lower-cased name to Linear's spelling; a label that cannot be made is left out and the user
    gets one notice."""
    used = sorted({label for task in tasks for label in task.labels})
    if not used:
        return {}
    existing = await read_label_names(tools.get(LIST_LABELS))
    if existing is None:
        await _notify_labels_skipped(context)
        return {}
    usable = {name.casefold(): name for name in existing}
    skipped = False
    for name in labels_to_create(used, existing):
        try:
            # The MCP adapter hands a tool's error back as text, so an answer without an id
            # (what a created label always carries) means the label was not made.
            parse_saved_item(
                await call_tool(tools, CREATE_LABEL, label_args(name, team_id), "label")
            )
        except UpstreamError as exc:
            if _stops(exc):
                raise
            skipped = True
            continue
        usable[name.casefold()] = name
        logger.info("export.label_created")
    if skipped:
        await _notify_labels_skipped(context)
    return usable


async def _notify_labels_skipped(context: McpRunContext) -> None:
    await publish(
        str(context.run_id),
        RunEventType.NOTICE,
        {"code": NOTICE_LABELS_SKIPPED, "text": NOTICE_LABELS_SKIPPED_TEXT},
        redis=context.redis,
    )


async def _task_refs(context: McpRunContext, tasks: list[Task]) -> dict[UUID, ExternalRef]:
    async with context.open_session(context.workspace_id) as session:
        return await integrations.list_external_refs(
            session, context.workspace_id, _PROVIDER, LocalKind.TASK, [t.id for t in tasks]
        )


def _stops(exc: UpstreamError) -> bool:
    return failure_reason(exc) in _STOPPING_REASONS


def _failed(kind: str, task: Task, reason: str) -> dict[str, str]:
    return {
        "kind": kind,
        "local_id": str(task.id),
        "name": issue_title(task.title),
        "reason": reason,
    }


# ---------------------------------------------------------------------------------- adapters
# Linear's ``save_issue`` argument shapes live here only.


def _issue_args(
    source: IssueSource, task: Task, inputs: _IssueInputs, parent_id: str | None
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "team": source.team_id,
        "project": source.project_id,
        "title": issue_title(task.title),
        "description": issue_description(task.description, source.idea_url),
        "estimate": task.estimate,
    }
    milestone = inputs.milestones.get(task.id)
    if milestone is not None:
        arguments["projectMilestone"] = milestone
    labels = labels_for(task, inputs.usable_labels)
    if labels:
        arguments["labels"] = labels
    if parent_id is not None:
        arguments["parentId"] = parent_id
    if inputs.existing is not None:
        arguments["id"] = inputs.existing.external_id
    return arguments


def _links_args(issue_id: str, blocker_ids: list[str]) -> dict[str, Any]:
    return {"id": issue_id, "blockedBy": blocker_ids}
