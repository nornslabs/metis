"""FastAPI routes for the health module (controller layer).

This module is the HTTP controller - it handles HTTP requests/responses
and delegates to the service layer for business logic.

Path: server/metis/modules/health/api.py
- Controller: defines routes and request/response handling
- Delegates to: service.py (check_postgres_health, check_redis_health, run_health_checks)
- Uses: schemas.py (HealthResponse)
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from metis.modules.health.schemas import HealthResponse
from metis.modules.health.service import run_health_checks

# API router with /v1 prefix
router = APIRouter(prefix="/v1")


@router.get("/health", response_model=None)
async def health_check() -> HealthResponse | Response:
    """Check the health of the application and its dependencies.

    This is the public health endpoint used by:
    - Docker Compose health checks
    - CI pipelines
    - Deployment probes

    Returns:
        HealthResponse with overall status and individual check results.
        Returns HTTP 200 if healthy, HTTP 503 if any dependency is down.
    """
    result = await run_health_checks()

    if result.status == "down":
        return Response(
            content=result.model_dump_json(),
            media_type="application/json",
            status_code=503,
        )

    return result


__all__ = ["router", "health_check"]
