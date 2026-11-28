"""Export records: an external reference and the stored decision on one run's export."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from metis.helpers.dto import FrozenModel


class ExportStatus(StrEnum):
    """Matches the ``export_jobs.status`` CHECK. The approval step writes the first two, the
    writes move ``running`` to one of the last three (``partial``: some Linear items were saved
    and some failed)."""

    APPROVED = "approved"
    DECLINED = "declined"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


# A job in one of these statuses has ended; ``summary[RESULT_KEY]`` then holds its result.
FINISHED_STATUSES = frozenset({ExportStatus.SUCCEEDED, ExportStatus.PARTIAL, ExportStatus.FAILED})
RESULT_KEY = "result"


class LocalKind(StrEnum):
    """What a Metis record is, in ``external_refs.local_kind``."""

    IDEA = "idea"  # a Linear project
    PHASE = "phase"  # a Linear milestone
    TASK = "task"  # a Linear issue
    HLD = "hld"  # a Linear document; ``local_id`` is the idea id (one HLD document per idea)


class ExternalRef(FrozenModel):
    """A Metis record's id in an external tool."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    local_kind: str
    local_id: UUID
    external_id: str
    external_url: str | None


class ExportJob(FrozenModel):
    """The stored decision on a run's export."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: UUID
    idea_id: UUID
    plan_id: UUID
    run_id: UUID
    status: ExportStatus
    summary: dict[str, Any]
    decided_by: UUID
    decided_at: datetime
    finished_at: datetime | None = None

    @property
    def result(self) -> dict[str, Any]:
        """What the finished export saved (counts, failed items, project URL); empty before."""
        stored = self.summary.get(RESULT_KEY)
        return stored if isinstance(stored, dict) else {}


class ExportFailedItem(FrozenModel):
    """One item the export could not save, as shown to members. ``reason`` is a short code or
    sentence kept in the job's result; the web renders it as plain text."""

    kind: str
    name: str
    reason: str


class ExportSummary(FrozenModel):
    """The newest finished export of one idea: what it saved, where, and what failed."""

    idea_id: UUID
    status: ExportStatus
    project_url: str | None = None
    created: int = 0
    updated: int = 0
    links: int = 0
    failed: list[ExportFailedItem] = Field(default_factory=list)
    finished_at: datetime | None = None


class ExportSummaryList(FrozenModel):
    items: list[ExportSummary]
