"""What a specialist may do with an MCP provider's tools, and the approval gate for writes.

A policy names the tools a specialist may see, split in ``read`` and ``write``. Anything not
named is never loaded (default deny), so a tool the provider adds later reaches nobody. A write
runs only while the run's approval is recorded in an ``ApprovalLedger``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from metis.agent.supervisor import Specialist


class McpWriteRefused(Exception):
    """A write was attempted with no approval. The tool builder returns the message to the
    model as an error result (list this class in its ``refusals``); it never ends the loop."""


WRITE_NOT_APPROVED = (
    "This tool changes data in an external tool and the user has not approved it. "
    "Ask the user to approve the action first, then call it again."
)


@dataclass(frozen=True)
class McpToolPolicy:
    """The tools of one provider a specialist may use.

    ``required``: Linear must work for this specialist. When it cannot (the connection lapsed
    mid-step) the step fails with the provider's error; otherwise the tool answers that Linear
    is unavailable and the run carries on.
    """

    read: frozenset[str] = frozenset()
    write: frozenset[str] = frozenset()
    required: bool = False

    @property
    def allowed(self) -> frozenset[str]:
        return self.read | self.write


PLANNER_POLICY = McpToolPolicy(read=frozenset({"list_teams", "list_projects", "list_issues"}))
INTEGRATOR_POLICY = McpToolPolicy(
    read=frozenset({"list_teams", "list_issue_labels"}),
    write=frozenset({"save_project", "save_milestone", "save_issue", "create_issue_label"}),
    required=True,
)

_POLICIES: Mapping[Specialist, McpToolPolicy] = {
    Specialist.PLANNER: PLANNER_POLICY,
    Specialist.INTEGRATOR: INTEGRATOR_POLICY,
}


def policy_for(specialist: Specialist) -> McpToolPolicy:
    """The specialist's policy; an empty one (no tools) when it has none."""
    return _POLICIES.get(specialist, McpToolPolicy())


class ApprovalLedger:
    """Whether the user approved the external writes of the current export.

    Held for one visit of a node. It starts from the run's ``pending_approval`` (so a node
    re-run after approval stays approved) and ``grant`` records a new approval; the node
    copies ``record`` to ``pending_approval`` and clears it when the export ends.
    """

    def __init__(self, pending_approval: Mapping[str, Any] | None = None) -> None:
        self._record: dict[str, Any] | None = (
            dict(pending_approval)
            if pending_approval is not None and pending_approval.get("approved") is True
            else None
        )

    @property
    def approved(self) -> bool:
        return self._record is not None

    @property
    def record(self) -> dict[str, Any] | None:
        """The ``pending_approval`` value for state: ``{action, details, approved: True}``."""
        return None if self._record is None else dict(self._record)

    def grant(self, action: str, details: str) -> None:
        self._record = {"action": action, "details": details, "approved": True}

    def require(self) -> None:
        if self._record is None:
            raise McpWriteRefused(WRITE_NOT_APPROVED)
