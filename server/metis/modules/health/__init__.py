"""Health module for liveness/readiness checks.

This module follows the controller-service pattern:
- __init__.py: exports all public symbols
- dto.py: response models (data structures)
- service.py: business logic (health checks)
- controller.py: HTTP controller (routes)
"""

from metis.modules.health.controller import health_check, router
from metis.modules.health.dto import HealthResponse, HealthStatus
from metis.modules.health.service import (
    check_postgres_health,
    check_redis_health,
    get_version,
    run_health_checks,
)

__all__ = [
    "HealthResponse",
    "HealthStatus",
    "check_postgres_health",
    "check_redis_health",
    "get_version",
    "health_check",
    "router",
    "run_health_checks",
]
