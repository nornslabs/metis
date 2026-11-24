"""Reads from Linear for the export: the teams and the labels. Output of the loaded MCP tools
is text; this checks its shape before the Integrator uses it (it is untrusted data)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool

from metis.core.errors import UpstreamError
from metis.core.logging import get_logger
from metis.helpers.http import FailureReason, provider_error
from metis.modules.integrations import IntegrationProvider

LIST_TEAMS = "list_teams"
LIST_LABELS = "list_issue_labels"
_LIST_KEYS = ("teams", "labels", "nodes", "items", "results")

logger = get_logger(__name__)


def parse_teams(text: str) -> list[dict[str, str]]:
    """``[{id, name, key}]`` from the tool's text. Entries without an id or name are dropped."""
    teams: list[dict[str, str]] = []
    for entry in _entries(text):
        team_id, name = entry.get("id"), entry.get("name")
        if isinstance(team_id, str) and team_id and isinstance(name, str) and name:
            key = entry.get("key")
            teams.append({"id": team_id, "name": name, "key": key if isinstance(key, str) else ""})
    return teams


def parse_label_names(text: str) -> list[str] | None:
    """The label names in the tool's text, or ``None`` when it is not a list of labels (a long
    list is cut before it reaches us, so the preview then leaves labels unchecked)."""
    entries = _entries(text)
    if not entries:
        return None if not _is_empty_list(text) else []
    return [e["name"] for e in entries if isinstance(e.get("name"), str)]


async def read_teams(tool: BaseTool | None) -> list[dict[str, str]]:
    """The workspace's Linear teams; a missing tool or unreadable answer is a provider failure."""
    if tool is None:
        raise provider_error(IntegrationProvider.LINEAR.value, FailureReason.BAD_RESPONSE)
    text = str(await tool.ainvoke({}))
    teams = parse_teams(text)
    if not teams and not _is_empty_list(text):
        raise provider_error(IntegrationProvider.LINEAR.value, FailureReason.BAD_RESPONSE)
    return teams


async def read_label_names(tool: BaseTool | None) -> list[str] | None:
    """Linear's label names, or ``None`` when they cannot be read (the preview then shows labels
    unchecked). An expired connection still raises."""
    if tool is None:
        return None
    try:
        return parse_label_names(str(await tool.ainvoke({})))
    except UpstreamError:
        logger.warning("export.labels_unreadable")
        return None


def _entries(text: str) -> list[dict[str, Any]]:
    try:
        data: Any = json.loads(text)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = next((data[k] for k in _LIST_KEYS if isinstance(data.get(k), list)), [])
    if not isinstance(data, list):
        return []
    return [entry for entry in data if isinstance(entry, dict)]


def _is_empty_list(text: str) -> bool:
    try:
        data: Any = json.loads(text)
    except ValueError:
        return False
    if isinstance(data, dict):
        data = next((data[k] for k in _LIST_KEYS if isinstance(data.get(k), list)), None)
    return bool(data == [])
