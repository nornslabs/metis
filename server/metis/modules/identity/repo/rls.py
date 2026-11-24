"""Row-level-security context for the request session."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.db import set_setting
from metis.core.errors import MetisError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from uuid import UUID


@asynccontextmanager
async def context(session: AsyncSession, setting: str, value: UUID) -> AsyncGenerator[None]:
    """Set an RLS setting for the block, then restore the caller's value.

    The setting is transaction-local. It is restored after success and after a
    domain error (the transaction is still usable); after a database error the
    transaction is aborted, so there is nothing left to restore.
    """
    previous = await session.scalar(
        text("SELECT current_setting(:setting, true)"), {"setting": setting}
    )
    await set_setting(session, setting, str(value))
    try:
        yield
    except MetisError:
        await set_setting(session, setting, previous or "")
        raise
    await set_setting(session, setting, previous or "")
