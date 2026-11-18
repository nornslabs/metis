"""Postgres access for ``ideas.interview_turns``. Queries only; no business rules.

Every query filters by ``workspace_id`` as well as relying on RLS. Turns are ordered by
their uuid7 ``id``.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import ReturningInsert

from metis.core.db import insert_or_none
from metis.helpers.ids import uuid7
from metis.modules.ideas.models import InterviewTurnRow

ASKED = "asked"


async def create(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    run_id: UUID,
    *,
    topic: str,
    source: str,
    question: str,
    answer: str | None,
) -> InterviewTurnRow:
    stmt = _insert(workspace_id, idea_id, run_id, topic, source, question, answer)
    return (await session.scalars(stmt)).one()


async def create_open_question_or_none(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    run_id: UUID,
    *,
    topic: str,
    question: str,
) -> InterviewTurnRow | None:
    """An unanswered asked turn; ``None`` when the run already has one (unique index)."""
    stmt = _insert(workspace_id, idea_id, run_id, topic, ASKED, question, None)
    return await insert_or_none(session, stmt)


async def get_open_question(
    session: AsyncSession, workspace_id: UUID, run_id: UUID
) -> InterviewTurnRow | None:
    stmt = select(InterviewTurnRow).where(
        InterviewTurnRow.workspace_id == workspace_id,
        InterviewTurnRow.run_id == run_id,
        InterviewTurnRow.source == ASKED,
        InterviewTurnRow.answer.is_(None),
    )
    return (await session.scalars(stmt.execution_options(populate_existing=True))).one_or_none()


async def get(session: AsyncSession, workspace_id: UUID, turn_id: UUID) -> InterviewTurnRow | None:
    stmt = select(InterviewTurnRow).where(
        InterviewTurnRow.workspace_id == workspace_id, InterviewTurnRow.id == turn_id
    )
    return (await session.scalars(stmt.execution_options(populate_existing=True))).one_or_none()


async def answer(
    session: AsyncSession, workspace_id: UUID, turn_id: UUID, text: str
) -> InterviewTurnRow | None:
    """Set the answer of a still-open turn; ``None`` when it is answered or unknown."""
    stmt = (
        update(InterviewTurnRow)
        .where(
            InterviewTurnRow.workspace_id == workspace_id,
            InterviewTurnRow.id == turn_id,
            InterviewTurnRow.answer.is_(None),
        )
        .values(answer=text)
        .returning(InterviewTurnRow)
    )
    return (await session.scalars(stmt)).one_or_none()


async def list_for_idea(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID
) -> list[InterviewTurnRow]:
    stmt = (
        select(InterviewTurnRow)
        .where(InterviewTurnRow.workspace_id == workspace_id, InterviewTurnRow.idea_id == idea_id)
        .order_by(InterviewTurnRow.id)
    )
    return list(await session.scalars(stmt))


def _insert(
    workspace_id: UUID,
    idea_id: UUID,
    run_id: UUID,
    topic: str,
    source: str,
    question: str,
    answer: str | None,
) -> ReturningInsert[InterviewTurnRow]:
    return (
        insert(InterviewTurnRow)
        .values(
            id=uuid7(),
            workspace_id=workspace_id,
            idea_id=idea_id,
            run_id=run_id,
            topic=topic,
            source=source,
            question=question,
            answer=answer,
        )
        .returning(InterviewTurnRow)
    )
