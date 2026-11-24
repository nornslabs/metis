"""Export records: an external reference and the stored decision on one run's export."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import ConfigDict

from metis.helpers.dto import FrozenModel


class ExportStatus(StrEnum):
    """Matches the ``export_jobs.status`` CHECK. The approval step writes the first two."""

    APPROVED = "approved"
    DECLINED = "declined"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LocalKind(StrEnum):
    """What a Metis record is, in ``external_refs.local_kind``."""

    IDEA = "idea"  # a Linear project
    PHASE = "phase"  # a Linear milestone
    TASK = "task"  # a Linear issue


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
