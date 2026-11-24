"""Setup helpers for the scoring tests: marks for all six parameters, sessions, the outbox."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.core.db import set_workspace
from metis.helpers.validation import validate_input
from metis.modules.scoring import NewParamScore, ScoreParam

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping
    from uuid import UUID

Sessions = async_sessionmaker[AsyncSession]

EVIDENCE = [{"url": "https://example.com/report", "title": "Report", "quote": "A quote."}]


def param(name: ScoreParam, **fields: Any) -> NewParamScore:
    """One valid parameter mark (raw 5, one source); ``fields`` override it."""
    data: dict[str, Any] = {
        "param": name,
        "raw": 5,
        "reason": f"Why {name.value} is what it is.",
        "confidence": 0.7,
        "evidence": EVIDENCE,
    }
    data.update(fields)
    return validate_input(NewParamScore, **data)


def marks(raws: Mapping[ScoreParam, int] | int = 5, **overrides: Any) -> list[NewParamScore]:
    """All six parameters; ``raws`` is one mark for all or a mark per parameter."""
    return [
        param(name, raw=raws if isinstance(raws, int) else raws[name], **overrides)
        for name in ScoreParam
    ]


@asynccontextmanager
async def in_workspace(sessions: Sessions, workspace_id: UUID) -> AsyncGenerator[AsyncSession]:
    """One committed transaction as ``metis_app``, scoped to ``workspace_id``."""
    async with sessions() as session, session.begin():
        await set_workspace(session, workspace_id)
        yield session


async def outbox_events(engine: AsyncEngine, workspace_id: UUID) -> list[dict[str, Any]]:
    """The workspace's ``ScoreComputed`` payloads, oldest first, read as the DB owner."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT payload FROM core.outbox WHERE workspace_id = :ws "
                "AND type = 'ScoreComputed' ORDER BY id"
            ),
            {"ws": workspace_id},
        )
        return [row[0] for row in result.all()]
