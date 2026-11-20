"""``transition`` and the transition table (no route yet, so the service seam), and list cursors."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import product
from uuid import UUID, uuid4

import httpx
import pytest
from idea_helpers import create, owner
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from metis.core.errors import ConflictError, IdeaNotFoundError, IllegalTransition, InvalidInputError
from metis.modules import ideas
from metis.modules.ideas.dto import Stage
from metis.modules.ideas.helpers.cursor import decode_cursor, encode_cursor
from metis.modules.ideas.helpers.transitions import ALLOWED_TRANSITIONS

S = Stage
LEGAL_MOVES = {
    (S.INTAKE, S.INTERVIEWING),
    (S.INTERVIEWING, S.RESEARCHING),
    (S.RESEARCHING, S.SCORING),
    (S.SCORING, S.ADVISING),
    (S.SCORING, S.SPEC_DRAFT),
    (S.ADVISING, S.INTERVIEWING),
    (S.ADVISING, S.RESEARCHING),
    (S.ADVISING, S.SCORING),
    (S.ADVISING, S.SPEC_DRAFT),
    (S.SPEC_DRAFT, S.SPEC_CONFIRMED),
    (S.SPEC_CONFIRMED, S.SPEC_DRAFT),
    (S.SPEC_CONFIRMED, S.PLANNING),
    (S.PLANNING, S.EXPORTED),
    (S.EXPORTED, S.PLANNING),
}
ALL_MOVES = set(product(Stage, Stage))


def test_the_table_allows_exactly_the_agreed_moves() -> None:
    actual = {(src, dst) for src, targets in ALLOWED_TRANSITIONS.items() for dst in targets}

    assert actual == LEGAL_MOVES
    assert set(ALLOWED_TRANSITIONS) == set(Stage)


@pytest.mark.parametrize(
    ("source", "target"), sorted(ALL_MOVES - LEGAL_MOVES, key=lambda m: (m[0].value, m[1].value))
)
async def test_an_illegal_move_raises(
    client: httpx.AsyncClient, engine: AsyncEngine, source: Stage, target: Stage
) -> None:
    ada = await owner(client, engine)
    idea_id = await _idea_at(client, engine, ada, source)

    async with AsyncSession(engine) as session:
        with pytest.raises(IllegalTransition) as caught:
            await ideas.transition(session, UUID(ada.workspace_id), idea_id, target)

    assert caught.value.status == 409
    assert caught.value.code == "idea.invalid_transition"
    assert (await _stage(engine, idea_id)) == source


@pytest.mark.parametrize(
    ("source", "target"), sorted(LEGAL_MOVES, key=lambda m: (m[0].value, m[1].value))
)
async def test_a_legal_move_changes_the_stage_and_bumps_the_version(
    client: httpx.AsyncClient, engine: AsyncEngine, source: Stage, target: Stage
) -> None:
    ada = await owner(client, engine)
    idea_id = await _idea_at(client, engine, ada, source)
    before = await _version(engine, idea_id)

    async with AsyncSession(engine) as session:
        moved = await ideas.transition(session, UUID(ada.workspace_id), idea_id, target)
        await session.commit()

    assert moved.stage is target
    assert moved.version == before + 1
    assert await _stage(engine, idea_id) is target


async def test_transition_of_an_unknown_or_foreign_idea_is_not_found(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine, "ada")
    bob = await owner(client, engine, "bob")
    created = await create(client, ada)

    async with AsyncSession(engine) as session:
        with pytest.raises(IdeaNotFoundError):
            await ideas.transition(session, UUID(ada.workspace_id), uuid4(), S.INTERVIEWING)
        with pytest.raises(IdeaNotFoundError):
            await ideas.transition(
                session, UUID(bob.workspace_id), UUID(created["id"]), S.INTERVIEWING
            )


async def test_transition_does_not_clobber_a_concurrent_edit(
    client: httpx.AsyncClient, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    ada = await owner(client, engine)
    created = await create(client, ada)
    idea_id = UUID(created["id"])

    from metis.modules.ideas import repo  # noqa: PLC0415

    real = repo.ideas.update_at_version

    async def edited_first(session: AsyncSession, *args: object, **kwargs: object) -> object:
        await real(session, UUID(ada.workspace_id), idea_id, version=1, changes={"title": "Other"})
        return await real(session, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(repo.ideas, "update_at_version", edited_first)

    async with AsyncSession(engine) as session:
        with pytest.raises(ConflictError):
            await ideas.transition(session, UUID(ada.workspace_id), idea_id, S.INTERVIEWING)


# ------------------------------------------------------------------ cursor


def test_a_cursor_round_trips() -> None:
    stamp = datetime(2026, 11, 16, 12, 30, 45, 123456, tzinfo=UTC)
    row_id = uuid4()

    assert decode_cursor(encode_cursor(stamp, row_id)) == (stamp, row_id)


@pytest.mark.parametrize("cursor", ["", "garbage", "////", "YWJj", "MjAyNi0xMS0xNnxub3QtYS11dWlk"])
def test_a_bad_cursor_is_invalid_input(cursor: str) -> None:
    with pytest.raises(InvalidInputError):
        decode_cursor(cursor)


# ------------------------------------------------------------------ helpers


async def _idea_at(
    client: httpx.AsyncClient, engine: AsyncEngine, caller: object, stage: Stage
) -> UUID:
    from sqlalchemy import text  # noqa: PLC0415

    created = await create(client, caller)  # type: ignore[arg-type]
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE ideas.ideas SET stage = :stage WHERE id = :id"),
            {"stage": stage.value, "id": created["id"]},
        )
    return UUID(created["id"])


async def _stage(engine: AsyncEngine, idea_id: UUID) -> Stage:
    from sqlalchemy import text  # noqa: PLC0415

    async with engine.connect() as conn:
        value = await conn.scalar(
            text("SELECT stage FROM ideas.ideas WHERE id = :id"), {"id": idea_id}
        )
    return Stage(value)


async def _version(engine: AsyncEngine, idea_id: UUID) -> int:
    from sqlalchemy import text  # noqa: PLC0415

    async with engine.connect() as conn:
        value = await conn.scalar(
            text("SELECT version FROM ideas.ideas WHERE id = :id"), {"id": idea_id}
        )
    assert isinstance(value, int)
    return value


# ------------------------------------------------------------------------- apply_revision


async def _raw_text(engine: AsyncEngine, idea_id: UUID) -> str:
    async with AsyncSession(engine) as session:
        idea = await ideas.get_idea(session, await _workspace_of(engine, idea_id), idea_id)
    return idea.raw_text


async def _workspace_of(engine: AsyncEngine, idea_id: UUID) -> UUID:
    from sqlalchemy import text

    async with engine.connect() as conn:
        value = await conn.scalar(
            text("SELECT workspace_id FROM ideas.ideas WHERE id = :id"), {"id": idea_id}
        )
    return UUID(str(value))


async def test_a_revision_replaces_the_text_and_bumps_the_version(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    idea_id = UUID((await create(client, ada))["id"])
    before = await _version(engine, idea_id)

    async with AsyncSession(engine) as session:
        revised = await ideas.apply_revision(
            session, UUID(ada.workspace_id), idea_id, "  A CRM that also sends invoices.  "
        )
        await session.commit()

    assert revised.raw_text == "A CRM that also sends invoices."
    assert revised.version == before + 1
    assert await _raw_text(engine, idea_id) == "A CRM that also sends invoices."


async def test_repeating_a_revision_changes_nothing(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    idea_id = UUID((await create(client, ada))["id"])
    workspace_id = UUID(ada.workspace_id)

    async with AsyncSession(engine) as session:
        await ideas.apply_revision(session, workspace_id, idea_id, "A CRM that sends invoices.")
        await session.commit()
    version = await _version(engine, idea_id)
    async with AsyncSession(engine) as session:
        again = await ideas.apply_revision(
            session, workspace_id, idea_id, "A CRM that sends invoices."
        )
        await session.commit()

    assert again.version == version == await _version(engine, idea_id)


@pytest.mark.parametrize("text", ["", "   ", "too short", "x" * 10_001])
async def test_a_revision_keeps_the_idea_text_bounds(
    client: httpx.AsyncClient, engine: AsyncEngine, text: str
) -> None:
    ada = await owner(client, engine)
    idea_id = UUID((await create(client, ada))["id"])

    async with AsyncSession(engine) as session:
        with pytest.raises(InvalidInputError):
            await ideas.apply_revision(session, UUID(ada.workspace_id), idea_id, text)


async def test_a_revision_of_an_unknown_or_foreign_idea_is_not_found(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine, "ada")
    bob = await owner(client, engine, "bob")
    created = await create(client, ada)

    async with AsyncSession(engine) as session:
        with pytest.raises(IdeaNotFoundError):
            await ideas.apply_revision(session, UUID(ada.workspace_id), uuid4(), "A new idea text.")
        with pytest.raises(IdeaNotFoundError):
            await ideas.apply_revision(
                session, UUID(bob.workspace_id), UUID(created["id"]), "A new idea text."
            )
