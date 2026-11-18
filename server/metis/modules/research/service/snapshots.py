"""Research snapshot rules: one open snapshot per run, sourced items, immutable once closed.

Every function takes the caller's ``AsyncSession``, flushes but never commits and is scoped
to the workspace id as well as RLS. ``open_snapshot`` is safe to call again with the same
arguments: the Researcher's node re-runs from its start when a paused run resumes.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import (
    CompetitorNotFoundError,
    IdeaNotFoundError,
    ResearchSourceMissingError,
    RunNotFoundError,
    SnapshotClosedError,
    SnapshotNotFoundError,
)
from metis.helpers.validation import validate_input
from metis.modules import ideas
from metis.modules.research import repo
from metis.modules.research.dto import (
    SOURCED_KINDS,
    CompetitorLink,
    LinkedCompetitor,
    NewResearchItem,
    ResearchItem,
    ResearchSnapshot,
    ResearchView,
    SnapshotClose,
)
from metis.modules.research.models import SnapshotRow


async def open_snapshot(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, run_id: UUID
) -> ResearchSnapshot:
    """The run's open snapshot, or a new one.

    Unknown or archived idea → ``IdeaNotFoundError``; a run of another idea (or none) →
    ``RunNotFoundError``.
    """
    await ideas.get_idea(session, workspace_id, idea_id)
    run = await ideas.get_run(session, workspace_id, run_id)
    if run.idea_id != idea_id:
        raise RunNotFoundError()
    row = await repo.snapshots.get_open_for_run(session, workspace_id, run_id)
    if row is None:
        row = await repo.snapshots.create_open_or_none(session, workspace_id, idea_id, run_id)
    if row is None:  # a parallel call opened one first
        row = await repo.snapshots.get_open_for_run(session, workspace_id, run_id)
    if row is None:
        raise SnapshotClosedError("The run's snapshot closed while it was being opened.")
    return ResearchSnapshot.model_validate(row)


async def add_item(
    session: AsyncSession, workspace_id: UUID, snapshot_id: UUID, item: NewResearchItem
) -> ResearchItem:
    """Add a finding to an open snapshot. Competitors and market facts need a ``url``."""
    if item.kind in SOURCED_KINDS and item.url is None:
        raise ResearchSourceMissingError(f"A {item.kind.value} item needs a source URL.")
    await _open_row(session, workspace_id, snapshot_id)
    row = await repo.items.create(
        session,
        workspace_id,
        snapshot_id,
        kind=item.kind.value,
        title=item.title,
        url=item.url,
        published_at=item.published_at,
        quote=item.quote,
        claim=item.claim,
        confidence=item.confidence,
    )
    return ResearchItem.model_validate(row)


async def link_competitor(
    session: AsyncSession,
    workspace_id: UUID,
    snapshot_id: UUID,
    competitor_id: UUID,
    overlap: float,
) -> LinkedCompetitor:
    """Record that an open snapshot found ``competitor_id`` for its idea, overlap 0–1.

    Linking again replaces the overlap.
    """
    link = validate_input(CompetitorLink, overlap=overlap)
    snapshot = await _open_row(session, workspace_id, snapshot_id)
    competitor = await repo.competitors.get(session, workspace_id, competitor_id)
    if competitor is None:
        raise CompetitorNotFoundError()
    await repo.idea_competitors.upsert(
        session,
        workspace_id,
        snapshot_id=snapshot_id,
        idea_id=snapshot.idea_id,
        competitor_id=competitor_id,
        overlap=link.overlap,
    )
    return LinkedCompetitor.model_validate(
        {**_competitor_fields(competitor), "overlap": link.overlap}
    )


async def close_snapshot(
    session: AsyncSession, workspace_id: UUID, snapshot_id: UUID, summary: str
) -> ResearchSnapshot:
    """Close an open snapshot with its summary; it is immutable from then on."""
    close = validate_input(SnapshotClose, summary=summary)
    await _open_row(session, workspace_id, snapshot_id)
    row = await repo.snapshots.close(session, workspace_id, snapshot_id, close.summary)
    if row is None:
        raise SnapshotClosedError()
    return ResearchSnapshot.model_validate(row)


async def latest_snapshot(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID
) -> ResearchView | None:
    """The idea's newest closed snapshot, or ``None``; an open one is never returned.

    Unknown or archived idea → ``IdeaNotFoundError``.
    """
    await ideas.get_idea(session, workspace_id, idea_id)
    row = await repo.snapshots.latest_closed(session, workspace_id, idea_id)
    return None if row is None else await _view(session, workspace_id, row)


async def get_snapshot(
    session: AsyncSession, workspace_id: UUID, snapshot_id: UUID
) -> ResearchView:
    """A snapshot, open or closed, with its items and competitors."""
    row = await _live_row(session, workspace_id, snapshot_id)
    return await _view(session, workspace_id, row)


async def _live_row(
    session: AsyncSession, workspace_id: UUID, snapshot_id: UUID, *, for_share: bool = False
) -> SnapshotRow:
    """The snapshot of a live idea, else ``SnapshotNotFoundError``."""
    row = await repo.snapshots.get(session, workspace_id, snapshot_id, for_share=for_share)
    if row is None:
        raise SnapshotNotFoundError()
    try:
        await ideas.get_idea(session, workspace_id, row.idea_id)
    except IdeaNotFoundError:
        raise SnapshotNotFoundError() from None
    return row


async def _open_row(session: AsyncSession, workspace_id: UUID, snapshot_id: UUID) -> SnapshotRow:
    """The snapshot, locked against closing until the caller's transaction ends."""
    row = await _live_row(session, workspace_id, snapshot_id, for_share=True)
    if row.closed_at is not None:
        raise SnapshotClosedError()
    return row


async def _view(session: AsyncSession, workspace_id: UUID, row: SnapshotRow) -> ResearchView:
    items = await repo.items.list_for_snapshot(session, workspace_id, row.id)
    linked = await repo.idea_competitors.list_for_snapshot(session, workspace_id, row.id)
    return ResearchView.model_validate(
        {
            **ResearchSnapshot.model_validate(row).model_dump(),
            "items": [ResearchItem.model_validate(item) for item in items],
            "competitors": [
                {**_competitor_fields(competitor), "overlap": overlap}
                for competitor, overlap in linked
            ],
        }
    )


def _competitor_fields(row: object) -> dict[str, object]:
    fields = ("id", "name", "url", "domain", "description", "pricing", "updated_at")
    return {name: getattr(row, name) for name in fields}
