"""The HLD written for a spec version: save and read.

Every function takes the caller's ``AsyncSession``, flushes but never commits, and is scoped to
the workspace id as well as RLS. An HLD is immutable and belongs to one spec version; a changed
spec gets a new one. ``stale`` is worked out on read by comparing the hash of the idea's latest
spec text with the hash the HLD was written for, so an edit that is reverted is not stale.
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.logging import get_logger
from metis.modules.ideas import repo
from metis.modules.ideas.dto.spec_hld import NewSpecHld, SpecHld

logger = get_logger(__name__)


def spec_hash(content_md: str) -> str:
    """The hash an HLD records for the spec text it was written for."""
    return hashlib.sha256(content_md.strip().encode("utf-8")).hexdigest()


async def save_spec_hld(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, data: NewSpecHld
) -> SpecHld:
    """Save the HLD for ``data.spec_version_number``; the one already saved for that version is
    returned unchanged, so a node re-run adds nothing."""
    existing = await repo.spec_hlds.get_by_number(
        session, workspace_id, idea_id, data.spec_version_number
    )
    if existing is not None:
        return SpecHld.model_validate(existing)
    row = await repo.spec_hlds.create(
        session,
        workspace_id,
        idea_id,
        spec_version_number=data.spec_version_number,
        spec_hash=data.spec_hash,
        build_language=data.build_language,
        content_md=data.content_md,
    )
    logger.info("spec.hld_saved", idea_id=str(idea_id), number=data.spec_version_number)
    return SpecHld.model_validate(row)


async def latest_spec_hld(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, latest_spec_hash: str
) -> SpecHld | None:
    """The newest HLD of the idea, marked ``stale`` when ``latest_spec_hash`` (the hash of the
    latest spec text) is not the one it was written for; ``None`` while there is none."""
    row = await repo.spec_hlds.latest(session, workspace_id, idea_id)
    if row is None:
        return None
    hld = SpecHld.model_validate(row)
    return hld.model_copy(update={"stale": row.spec_hash != latest_spec_hash})
