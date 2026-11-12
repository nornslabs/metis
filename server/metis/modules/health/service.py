"""Health check service functions for the health module.

This module is the service layer in the controller-service pattern:
- api.py: Controller (HTTP routes)
- service.py: Service (orchestration, business logic)
- repository.py: Repository (data access, connection handling)
- parse.py: Transformers (data normalization)

This module orchestrates health checks and returns results in the
response format expected by the controller.
"""

from __future__ import annotations

from metis.modules.health.parse import build_health_response, get_git_version
from metis.modules.health.repository import (
    check_postgres_connection,
    check_redis_connection,
)
from metis.modules.health.schemas import HealthResponse

# Re-export for backwards compatibility
__all__ = [
    "HealthResponse",
    "check_postgres_health",
    "check_redis_health",
    "get_version",
    "run_health_checks",
]


async def check_postgres_health() -> str:
    """Check Postgres connectivity.

    Delegates to repository for the actual connection check.

    Returns:
        "ok" if reachable, "down" otherwise
    """
    return await check_postgres_connection()


async def check_redis_health() -> str:
    """Check Redis connectivity.

    Delegates to repository for the actual connection check.

    Returns:
        "ok" if reachable, "down" otherwise
    """
    return await check_redis_connection()


def get_version() -> str:
    """Get the current git commit SHA.

    Delegates to parse module for version resolution.

    Returns:
        Git commit SHA or "unknown"
    """
    return get_git_version()


async def run_health_checks() -> HealthResponse:
    """Run all health checks and build the response.

    Orchestrates:
    1. Run postgres and redis checks concurrently
    2. Get the application version
    3. Build the health response

    Returns:
        HealthResponse with overall status and individual check results
    """
    db_status, redis_status = await check_postgres_health(), await check_redis_health()
    version = get_version()

    return build_health_response(
        db_status=db_status,
        redis_status=redis_status,
        version=version,
    )