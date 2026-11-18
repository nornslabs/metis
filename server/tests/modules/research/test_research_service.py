"""Research snapshots, items and the competitor KB at the research module's public seam.

Runs as ``metis_app`` (RLS on) against a migrated Postgres. The Researcher's tools
(SHIP-238) call these functions; the HTTP routes are covered in ``test_research_api.py``.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.core.errors import (
    CompetitorNotFoundError,
    IdeaNotFoundError,
    InvalidInputError,
    ResearchSourceMissingError,
    RunNotFoundError,
    SnapshotClosedError,
    SnapshotNotFoundError,
)
from metis.helpers.ids import uuid7
from metis.helpers.validation import validate_input
from metis.modules import research
from metis.modules.research import NewCompetitor, ResearchItemKind, ResearchSnapshot
from tests.modules.research.research_helpers import (
    Run,
    another_run,
    archive,
    competitor,
    in_workspace,
    item,
    new_run,
    vector,
)

Sessions = async_sessionmaker[AsyncSession]


async def _open(sessions: Sessions, run: Run) -> ResearchSnapshot:
    async with in_workspace(sessions, run.workspace_id) as session:
        return await research.open_snapshot(session, run.workspace_id, run.idea_id, run.run_id)


async def _close(
    sessions: Sessions, run: Run, snapshot_id: UUID, summary: str = "Crowded."
) -> None:
    async with in_workspace(sessions, run.workspace_id) as session:
        await research.close_snapshot(session, run.workspace_id, snapshot_id, summary)


async def _upsert(sessions: Sessions, workspace_id: UUID, new: NewCompetitor) -> UUID:
    async with in_workspace(sessions, workspace_id) as session:
        return (await research.upsert_competitor(session, workspace_id, new)).id


async def _competitor_count(engine: AsyncEngine, workspace_id: UUID) -> int:
    async with engine.connect() as conn:
        count = await conn.scalar(
            text("SELECT count(*) FROM research.competitors WHERE workspace_id = :ws"),
            {"ws": workspace_id},
        )
    return int(count)


# ------------------------------------------------------------------ snapshots
async def test_opening_a_snapshot_twice_for_one_run_returns_the_same_snapshot(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)

    first = await _open(app_sessions, run)
    second = await _open(app_sessions, run)

    assert second.id == first.id
    assert (first.idea_id, first.run_id, first.closed_at) == (run.idea_id, run.run_id, None)


async def test_a_run_gets_a_new_snapshot_after_its_last_one_closed(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    first = await _open(app_sessions, run)
    await _close(app_sessions, run, first.id)

    second = await _open(app_sessions, run)

    assert second.id != first.id


async def test_a_snapshot_needs_a_live_idea_and_a_run_of_that_idea(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    other = await another_run(engine, run.workspace_id)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        with pytest.raises(RunNotFoundError):
            await research.open_snapshot(session, run.workspace_id, run.idea_id, other.run_id)
    await archive(engine, run.idea_id)
    async with in_workspace(app_sessions, run.workspace_id) as session:
        with pytest.raises(IdeaNotFoundError):
            await research.open_snapshot(session, run.workspace_id, run.idea_id, run.run_id)


async def test_closing_sets_the_summary_and_a_closed_snapshot_cannot_change(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    snapshot = await _open(app_sessions, run)
    competitor_id = await _upsert(app_sessions, run.workspace_id, competitor())

    async with in_workspace(app_sessions, run.workspace_id) as session:
        closed = await research.close_snapshot(session, run.workspace_id, snapshot.id, " Crowded. ")
    assert closed.summary == "Crowded."
    assert closed.closed_at is not None

    async with in_workspace(app_sessions, run.workspace_id) as session:
        with pytest.raises(SnapshotClosedError):
            await research.add_item(session, run.workspace_id, snapshot.id, item())
        with pytest.raises(SnapshotClosedError):
            await research.link_competitor(
                session, run.workspace_id, snapshot.id, competitor_id, 0.5
            )
        with pytest.raises(SnapshotClosedError):
            await research.close_snapshot(session, run.workspace_id, snapshot.id, "Again.")


async def test_an_empty_summary_is_rejected(engine: AsyncEngine, app_sessions: Sessions) -> None:
    run = await new_run(engine)
    snapshot = await _open(app_sessions, run)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        with pytest.raises(InvalidInputError):
            await research.close_snapshot(session, run.workspace_id, snapshot.id, "   ")


# ---------------------------------------------------------------------- items
@pytest.mark.parametrize("kind", [ResearchItemKind.COMPETITOR, ResearchItemKind.MARKET_FACT])
async def test_competitors_and_market_facts_without_a_source_url_are_rejected(
    engine: AsyncEngine, app_sessions: Sessions, kind: ResearchItemKind
) -> None:
    run = await new_run(engine)
    snapshot = await _open(app_sessions, run)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        with pytest.raises(ResearchSourceMissingError):
            await research.add_item(
                session, run.workspace_id, snapshot.id, item(kind=kind, url=None)
            )


@pytest.mark.parametrize("kind", [ResearchItemKind.TREND, ResearchItemKind.RISK])
async def test_trends_and_risks_may_have_no_url(
    engine: AsyncEngine, app_sessions: Sessions, kind: ResearchItemKind
) -> None:
    run = await new_run(engine)
    snapshot = await _open(app_sessions, run)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        saved = await research.add_item(
            session, run.workspace_id, snapshot.id, item(kind=kind, url=None)
        )

    assert (saved.kind, saved.url) == (kind, None)


@pytest.mark.parametrize(
    "fields",
    [
        {"url": "ftp://example.com/file"},
        {"url": "javascript:alert(1)"},
        {"confidence": 1.5},
        {"confidence": -0.1},
        {"title": "  "},
        {"claim": "x" * 2_001},
    ],
)
def test_invalid_item_fields_are_rejected(fields: dict[str, object]) -> None:
    with pytest.raises(InvalidInputError):
        item(**fields)


async def test_items_are_written_to_an_unknown_snapshot_never(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        with pytest.raises(SnapshotNotFoundError):
            await research.add_item(session, run.workspace_id, uuid7(), item())


# ---------------------------------------------------------------- competitors
async def test_the_same_competitor_found_twice_is_stored_once_and_updated(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    first = await _upsert(app_sessions, run.workspace_id, competitor(description="A CRM."))

    async with in_workspace(app_sessions, run.workspace_id) as session:
        again = await research.upsert_competitor(
            session,
            run.workspace_id,
            competitor(name="Acme", url="http://ACME.com/", pricing="$9/month"),
        )

    assert again.id == first
    assert (again.name, again.domain) == ("Acme", "acme.com")
    assert (again.description, again.pricing) == ("A CRM.", "$9/month")
    assert await _competitor_count(engine, run.workspace_id) == 1


async def test_the_same_domain_in_two_workspaces_is_two_competitors(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await new_run(engine, "ada")
    grace = await new_run(engine, "grace")

    first = await _upsert(app_sessions, ada.workspace_id, competitor())
    second = await _upsert(app_sessions, grace.workspace_id, competitor())

    assert first != second


def test_an_embedding_of_the_wrong_size_is_rejected() -> None:
    with pytest.raises(InvalidInputError):
        competitor(embedding=[0.1, 0.2])


async def test_linking_a_competitor_ties_it_to_the_snapshot_with_its_overlap(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    snapshot = await _open(app_sessions, run)
    competitor_id = await _upsert(app_sessions, run.workspace_id, competitor())

    async with in_workspace(app_sessions, run.workspace_id) as session:
        await research.link_competitor(session, run.workspace_id, snapshot.id, competitor_id, 0.4)
        await research.link_competitor(session, run.workspace_id, snapshot.id, competitor_id, 0.7)
        with pytest.raises(CompetitorNotFoundError):
            await research.link_competitor(session, run.workspace_id, snapshot.id, uuid7(), 0.5)
        with pytest.raises(InvalidInputError):
            await research.link_competitor(
                session, run.workspace_id, snapshot.id, competitor_id, 1.2
            )
        view = await research.get_snapshot(session, run.workspace_id, snapshot.id)

    assert [(c.id, c.overlap) for c in view.competitors] == [(competitor_id, 0.7)]


# -------------------------------------------------------------------- KB lookup
async def test_kb_lookup_finds_competitors_by_name_and_domain_without_embeddings(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    acme = await _upsert(app_sessions, run.workspace_id, competitor())
    await _upsert(app_sessions, run.workspace_id, competitor(name="Bolt", url="https://bolt.io"))

    async with in_workspace(app_sessions, run.workspace_id) as session:
        by_name = await research.kb_lookup(session, run.workspace_id, "acme")
        by_domain = await research.kb_lookup(session, run.workspace_id, "bolt.io")
        wildcard = await research.kb_lookup(session, run.workspace_id, "%")

    assert [(m.competitor.id, m.matched_by) for m in by_name] == [(acme, "name")]
    assert [m.competitor.name for m in by_domain] == ["Bolt"]
    assert wildcard == []


async def test_kb_lookup_ranks_by_embedding_similarity_then_adds_name_matches(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    near = await _upsert(
        app_sessions,
        run.workspace_id,
        competitor(name="Near", url="https://near.dev", embedding=vector(1.0, 0.1)),
    )
    far = await _upsert(
        app_sessions,
        run.workspace_id,
        competitor(name="Far", url="https://far.dev", embedding=vector(0.0, 1.0)),
    )
    named = await _upsert(app_sessions, run.workspace_id, competitor(name="Pocket CRM"))

    async with in_workspace(app_sessions, run.workspace_id) as session:
        matches = await research.kb_lookup(
            session, run.workspace_id, "pocket", k=3, query_embedding=vector(1.0, 0.0)
        )

    assert [m.competitor.id for m in matches] == [near, far, named]
    assert [m.matched_by for m in matches] == ["embedding", "embedding", "name"]
    assert matches[0].score is not None and matches[0].score > 0.9
    assert matches[2].score is None


async def test_kb_lookup_returns_at_most_k_and_rejects_bad_input(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    for name in ("Acme One", "Acme Two", "Acme Three"):
        await _upsert(
            app_sessions,
            run.workspace_id,
            competitor(name=name, url=f"{name}.com".replace(" ", "")),
        )

    async with in_workspace(app_sessions, run.workspace_id) as session:
        matches = await research.kb_lookup(session, run.workspace_id, "acme", k=2)
        with pytest.raises(InvalidInputError):
            await research.kb_lookup(session, run.workspace_id, "acme", k=21)
        with pytest.raises(InvalidInputError):
            await research.kb_lookup(session, run.workspace_id, " ")
        with pytest.raises(InvalidInputError):
            await research.kb_lookup(session, run.workspace_id, "acme", query_embedding=[1.0])

    assert len(matches) == 2


# ----------------------------------------------------------------------- reads
async def test_latest_snapshot_is_the_newest_closed_one_with_its_items_and_competitors(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    old = await _open(app_sessions, run)
    await _close(app_sessions, run, old.id, "Old.")
    snapshot = await _open(app_sessions, run)
    competitor_id = await _upsert(app_sessions, run.workspace_id, competitor())
    async with in_workspace(app_sessions, run.workspace_id) as session:
        await research.add_item(session, run.workspace_id, snapshot.id, item(title="First"))
        await research.add_item(
            session, run.workspace_id, snapshot.id, item(kind="risk", url=None, title="Second")
        )
        await research.link_competitor(session, run.workspace_id, snapshot.id, competitor_id, 0.9)
    await _close(app_sessions, run, snapshot.id, "New.")
    await _open(app_sessions, run)  # a third snapshot, still open: never the latest

    async with in_workspace(app_sessions, run.workspace_id) as session:
        latest = await research.latest_snapshot(session, run.workspace_id, run.idea_id)

    assert latest is not None
    assert (latest.id, latest.summary) == (snapshot.id, "New.")
    assert [i.title for i in latest.items] == ["First", "Second"]
    assert [(c.id, c.domain, c.overlap) for c in latest.competitors] == [
        (competitor_id, "acme.com", 0.9)
    ]


async def test_an_idea_without_closed_research_has_no_latest_snapshot(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    await _open(app_sessions, run)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        assert await research.latest_snapshot(session, run.workspace_id, run.idea_id) is None
        with pytest.raises(IdeaNotFoundError):
            await research.latest_snapshot(session, run.workspace_id, uuid7())


async def test_a_snapshot_of_an_archived_idea_is_not_found(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    snapshot = await _open(app_sessions, run)
    await archive(engine, run.idea_id)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        with pytest.raises(SnapshotNotFoundError):
            await research.get_snapshot(session, run.workspace_id, snapshot.id)
        with pytest.raises(SnapshotNotFoundError):
            await research.add_item(session, run.workspace_id, snapshot.id, item())


# ------------------------------------------------------------------------- RLS
async def test_another_workspace_sees_none_of_the_research(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await new_run(engine, "ada")
    grace = await new_run(engine, "grace")
    snapshot = await _open(app_sessions, ada)
    competitor_id = await _upsert(app_sessions, ada.workspace_id, competitor())
    await _close(app_sessions, ada, snapshot.id)

    async with in_workspace(app_sessions, grace.workspace_id) as session:
        with pytest.raises(SnapshotNotFoundError):
            await research.get_snapshot(session, grace.workspace_id, snapshot.id)
        assert await research.kb_lookup(session, grace.workspace_id, "acme") == []
        grace_snapshot = await research.open_snapshot(
            session, grace.workspace_id, grace.idea_id, grace.run_id
        )
        with pytest.raises(CompetitorNotFoundError):
            await research.link_competitor(
                session, grace.workspace_id, grace_snapshot.id, competitor_id, 0.5
            )
    # Even with the wrong workspace id passed in, RLS hides the rows.
    async with in_workspace(app_sessions, grace.workspace_id) as session:
        with pytest.raises(SnapshotNotFoundError):
            await research.get_snapshot(session, ada.workspace_id, snapshot.id)


def test_a_new_competitor_needs_a_name_and_a_web_url() -> None:
    with pytest.raises(InvalidInputError):
        validate_input(NewCompetitor, name=" ", url="https://acme.com")
    with pytest.raises(InvalidInputError):
        validate_input(NewCompetitor, name="Acme", url="not a url")
