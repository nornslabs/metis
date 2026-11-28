"""Unit tests for Linear MCP response parsing and schema-aware argument adaptation."""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.tools import StructuredTool

from metis.agent.tools.export_writes import call_tool, parse_saved_item
from metis.core.errors import UpstreamError


@pytest.mark.parametrize(
    ("payload", "expected_id", "expected_url"),
    [
        (
            {"success": True, "issue": {"id": "iss-1", "url": "https://linear.app/t/issue/ENG-1"}},
            "iss-1",
            "https://linear.app/t/issue/ENG-1",
        ),
        (
            {"success": True, "projectMilestone": {"id": "ms-1", "url": "https://linear.app/ms/1"}},
            "ms-1",
            "https://linear.app/ms/1",
        ),
        (
            {"success": True, "issueLabel": {"id": "lbl-1"}},
            "lbl-1",
            None,
        ),
        (
            {"success": True, "label": {"id": "lbl-2"}},
            "lbl-2",
            None,
        ),
    ],
)
def test_parse_saved_item_extracts_nested_linear_entities(
    payload: dict[str, object], expected_id: str, expected_url: str | None
) -> None:
    saved = parse_saved_item(json.dumps(payload))

    assert saved.external_id == expected_id
    assert saved.external_url == expected_url


def test_parse_saved_item_rejects_non_json_error_text() -> None:
    with pytest.raises(UpstreamError):
        parse_saved_item("MCP error -32602: Invalid arguments")


async def test_call_tool_adapts_linear_argument_names_to_tool_schema() -> None:
    seen: list[dict[str, Any]] = []

    async def fake_save_issue(**kwargs: Any) -> str:
        seen.append(kwargs)
        return json.dumps({"success": True, "issue": {"id": "iss-1"}})

    schema = {
        "type": "object",
        "properties": {
            "teamId": {"type": "string"},
            "projectId": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "milestone": {"type": "string"},
            "parent": {"type": "string"},
        },
        "additionalProperties": False,
    }
    tool = StructuredTool.from_function(
        coroutine=fake_save_issue,
        name="save_issue",
        description="Save issue",
        args_schema=schema,
    )

    result = await call_tool(
        {"save_issue": tool},
        "save_issue",
        {
            "team": "team-1",
            "project": "proj-1",
            "title": "Build API",
            "description": "Details",
            "projectMilestone": "ms-1",
            "parentId": "iss-0",
            "estimate": 3,
        },
        "issue",
    )

    assert parse_saved_item(result).external_id == "iss-1"
    assert seen == [
        {
            "teamId": "team-1",
            "projectId": "proj-1",
            "title": "Build API",
            "description": "Details",
            "milestone": "ms-1",
            "parent": "iss-0",
        }
    ]
