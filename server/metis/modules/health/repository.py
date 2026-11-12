"""Repository for database and connection operations.

This module handles low-level connection checking and query execution.
It abstracts the database-specific connection logic from the service layer.

Repository pattern: Service → Repository → External systems (DB, Redis)
"""

from __future__ import annotations

import asyncio

import asyncpg  # type: ignore[import-untyped]
import redis.asyncio as redis

from metis.core.config import get_settings
from metis.modules.health.schemas import HealthStatus


def to_asyncpg_dsn(url: str) -> str:
    """Strip the SQLAlchemy driver suffix so asyncpg accepts the DSN.

    DATABASE_URL uses ``postgresql+asyncpg://`` for SQLAlchemy, but
    ``asyncpg.connect`` only accepts ``postgresql://`` or ``postgres://``.
    """
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def query_postgres(dsn: str, query: str, timeout_secs: float = 1.0) -> bool:
    """Execute a query against PostgreSQL and return success status.

    Args:
        dsn: Database connection string
        query: SQL query to execute
        timeout_secs: Connection and query timeout in seconds

    Returns:
        True if query executed successfully, False otherwise
    """
    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn=dsn), timeout=timeout_secs)
        try:
            await conn.execute(query)
            return True
        except Exception:
            return False
        finally:
            try:
                await conn.close()
            except Exception:
                pass
    except Exception:
        return False


async def ping_redis(url: str, timeout_secs: float = 1.0) -> bool:
    """Ping Redis and return success status.

    Args:
        url: Redis connection URL
        timeout_secs: Ping timeout in seconds

    Returns:
        True if ping successful, False otherwise
    """
    try:
        client = redis.from_url(url)  # type: ignore[no-untyped-call]
        try:
            await asyncio.wait_for(client.ping(), timeout=timeout_secs)
            await client.close()
            return True
        except Exception:
            try:
                await client.close()
            except Exception:
                pass
            return False
    except Exception:
        return False


async def check_postgres_connection() -> str:
    """Check Postgres connectivity using the configured connection string.

    Returns:
        HealthStatus.OK if healthy, HealthStatus.DOWN otherwise
    """
    settings = get_settings()
    success = await query_postgres(
        dsn=to_asyncpg_dsn(settings.database_url),
        query="SELECT 1",
        timeout_secs=1.0,
    )
    return HealthStatus.OK if success else HealthStatus.DOWN


async def check_redis_connection() -> str:
    """Check Redis connectivity using the configured connection string.

    Returns:
        HealthStatus.OK if healthy, HealthStatus.DOWN otherwise
    """
    settings = get_settings()
    success = await ping_redis(
        url=settings.redis_url,
        timeout_secs=1.0,
    )
    return HealthStatus.OK if success else HealthStatus.DOWN


__all__ = [
    "check_postgres_connection",
    "check_redis_connection",
    "ping_redis",
    "query_postgres",
    "to_asyncpg_dsn",
]
