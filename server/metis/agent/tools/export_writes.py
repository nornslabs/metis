"""The Linear writes of the export's second step: the project, then one milestone per phase.

Each item is created or updated by what ``external_refs`` holds for it (a ref means update, none
means create), and its ref is committed in its own short transaction right after the Linear call,
so a crash or a retry carries on from what was saved and never creates an item twice. After each
saved item one ``export_progress`` event is published.

The shape of Linear's ``save_project`` and ``save_milestone`` arguments and answers is kept in the
four small adapter functions at the bottom, so a mismatch with the real server is a one-place fix.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain_core.tools import BaseTool

from metis.agent.tools.export_project import (
    ProjectScore,
    milestone_description,
    milestone_name,
    project_description,
    project_name,
)
from metis.agent.tools.mcp import McpRunContext
from metis.core.events import RunEventType, publish
from metis.core.logging import get_logger
from metis.helpers.http import FailureReason, provider_error
from metis.helpers.mcp import failure_reason
from metis.modules import integrations
from metis.modules.integrations import ExternalRef, IntegrationProvider, LocalKind
from metis.modules.planning import Phase, Plan

SAVE_PROJECT = "save_project"
SAVE_MILESTONE = "save_milestone"
ITEM_PROJECT = "project"
ITEM_MILESTONE = "milestone"
_PROVIDER = IntegrationProvider.LINEAR

logger = get_logger(__name__)


@dataclass(frozen=True)
class ProjectSource:
    """What the project and milestones are made from."""

    idea_id: UUID
    title: str
    url: str
    spec_text: str
    score: ProjectScore | None
    plan: Plan
    team_id: str


@dataclass(frozen=True)
class SavedItem:
    """A Linear item as the tool answered: its id and, when given, its url."""

    external_id: str
    external_url: str | None


async def write_project_and_milestones(
    context: McpRunContext, tools: dict[str, BaseTool], source: ProjectSource
) -> None:
    """Create or update the project and its milestones, in plan order.

    Stops at the first failure with the provider's error; what was saved stays saved, and the
    next export carries on from those refs.
    """
    phases = source.plan.phases
    refs = await _refs(context, source)
    total = 1 + len(phases)
    project_ref = refs.get(LocalKind.IDEA, {}).get(source.idea_id)
    project = await _save(
        context,
        tools,
        SAVE_PROJECT,
        _project_args(source, project_ref),
        LocalKind.IDEA,
        source.idea_id,
    )
    await _progress(context, ITEM_PROJECT, source.title, project_ref, 1, total)
    logger.info("export.project_saved", action=_action(project_ref))
    phase_refs = refs.get(LocalKind.PHASE, {})
    for index, phase in enumerate(phases):
        existing = phase_refs.get(phase.id)
        name = milestone_name(index, phase.name)
        await _save(
            context,
            tools,
            SAVE_MILESTONE,
            _milestone_args(project, index, name, phase, existing),
            LocalKind.PHASE,
            phase.id,
        )
        await _progress(context, ITEM_MILESTONE, name, existing, index + 2, total)
        logger.info("export.milestone_saved", phase_index=index, action=_action(existing))


async def _refs(
    context: McpRunContext, source: ProjectSource
) -> dict[LocalKind, dict[UUID, ExternalRef]]:
    async with context.open_session(context.workspace_id) as session:
        workspace_id = context.workspace_id
        return {
            LocalKind.IDEA: await integrations.list_external_refs(
                session, workspace_id, _PROVIDER, LocalKind.IDEA, [source.idea_id]
            ),
            LocalKind.PHASE: await integrations.list_external_refs(
                session,
                workspace_id,
                _PROVIDER,
                LocalKind.PHASE,
                [p.id for p in source.plan.phases],
            ),
        }


async def _save(
    context: McpRunContext,
    tools: dict[str, BaseTool],
    tool_name: str,
    arguments: dict[str, Any],
    local_kind: LocalKind,
    local_id: UUID,
) -> SavedItem:
    """Call the write tool, then commit the ref before returning (the next call comes after)."""
    tool = tools.get(tool_name)
    if tool is None:
        raise provider_error(_PROVIDER.value, FailureReason.BAD_RESPONSE)
    try:
        saved = _saved_item(str(await tool.ainvoke(arguments)))
    except Exception as exc:
        logger.warning(
            "export.write_failed", item=local_kind.value, reason=failure_reason(exc).value
        )
        raise
    async with context.open_session(context.workspace_id) as session:
        await integrations.save_external_ref(
            session,
            context.workspace_id,
            _PROVIDER,
            local_kind,
            local_id,
            saved.external_id,
            saved.external_url,
        )
    return saved


async def _progress(
    context: McpRunContext,
    item: str,
    name: str,
    existing: ExternalRef | None,
    done: int,
    total: int,
) -> None:
    await publish(
        str(context.run_id),
        RunEventType.EXPORT_PROGRESS,
        {"item": item, "name": name, "action": _action(existing), "done": done, "total": total},
        redis=context.redis,
    )


def _action(existing: ExternalRef | None) -> str:
    return "update" if existing is not None else "create"


# ---------------------------------------------------------------------------------- adapters
# Linear's MCP tool shapes live here only.


def _project_args(source: ProjectSource, existing: ExternalRef | None) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "name": project_name(source.title),
        "description": project_description(
            url=source.url,
            spec_text=source.spec_text,
            score=source.score,
            plan_version=source.plan.version,
        ),
    }
    if existing is None:
        arguments["addTeams"] = [source.team_id]
    else:
        arguments["id"] = existing.external_id
    return arguments


def _milestone_args(
    project: SavedItem,
    index: int,
    name: str,
    phase: Phase,
    existing: ExternalRef | None,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "project": project.external_id,
        "name": name,
        "description": milestone_description(phase.goal, phase.exit_criteria),
        "sortOrder": index,
    }
    if existing is not None:
        arguments["id"] = existing.external_id
    return arguments


def _saved_item(text: str) -> SavedItem:
    """The id and url in a save tool's answer; an answer with no id is a provider failure."""
    try:
        data: Any = json.loads(text)
    except ValueError:
        data = None
    entry = _entry(data)
    external_id = entry.get("id") if entry is not None else None
    if not isinstance(external_id, str) or not external_id:
        raise provider_error(_PROVIDER.value, FailureReason.BAD_RESPONSE)
    url = entry.get("url") if entry is not None else None
    return SavedItem(external_id, url if isinstance(url, str) and url else None)


def _entry(data: Any) -> dict[str, Any] | None:
    """The object holding ``id``: the answer itself, or the one nested under ``project`` or
    ``milestone``."""
    if not isinstance(data, dict):
        return None
    if "id" in data:
        return data
    for key in (ITEM_PROJECT, ITEM_MILESTONE):
        nested = data.get(key)
        if isinstance(nested, dict):
            return nested
    return None
