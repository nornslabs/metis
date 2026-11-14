"""Database session management for Metis.

Provides async SQLAlchemy engine, session factory, and helper utilities
for database connectivity. All connections use the non-superuser app role
configured via DATABASE_URL.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from metis.core.config import get_settings


def get_engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine.

    The engine is configured from DATABASE_URL via get_settings().
    """
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=False,  # Log SQL via structlog if needed
        pool_size=get_settings().db_pool_size,
        pool_pre_ping=True,  # Verify connections before use
    )


# Module-level engine singleton
_engine: AsyncEngine | None = None


def engine() -> AsyncEngine:
    """Return the singleton AsyncEngine."""
    global _engine
    if _engine is None:
        _engine = get_engine()
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return a sessionmaker bound to the engine."""
    return async_sessionmaker(
        engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


# Module-level sessionmaker singleton
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Return the singleton sessionmaker."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = get_sessionmaker()
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions.

    Use in route handlers: async with get_session() as session: ...
    """
    sm = get_session_maker()
    async with sm() as session:
        yield session


async def get_connection() -> AsyncGenerator[AsyncConnection, None]:
    """FastAPI dependency for raw database connections.

    Use for operations that need direct connection access (e.g., init scripts).
    """
    async with engine().connect() as conn:
        yield conn

# --------------------------------------------------------------- request scope
USER_SETTING = "app.user_id"
WORKSPACE_SETTING = "app.workspace_id"


@asynccontextmanager
async def transaction(session: AsyncSession) -> AsyncGenerator[AsyncSession]:
    """Commit ``session`` when the block succeeds; roll it back on any exception."""
    try:
        yield session
    except BaseException:
        await session.rollback()
        raise
    await session.commit()


async def get_request_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency: one session per request, committed before the response.

    Always depend on it through ``SessionDep`` (``scope="function"``), so the
    commit runs before the response is sent and a failed commit is a 500, not a
    200 for work that was never saved. Every dependency in the request shares it.
    """
    async with get_session_maker()() as session, transaction(session):
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_request_session, scope="function")]


async def set_setting(session: AsyncSession, setting: str, value: str) -> None:
    """Set a Postgres setting for the current transaction only."""
    await session.execute(
        text("SELECT set_config(:setting, :value, true)"), {"setting": setting, "value": value}
    )


async def set_workspace(session: AsyncSession, workspace_id: UUID) -> None:
    """Scope RLS-protected tenant tables to ``workspace_id`` for this transaction."""
    await set_setting(session, WORKSPACE_SETTING, str(workspace_id))


async def set_user(session: AsyncSession, user_id: UUID) -> None:
    """Expose the caller to user-scoped RLS policies for this transaction."""
    await set_setting(session, USER_SETTING, str(user_id))
