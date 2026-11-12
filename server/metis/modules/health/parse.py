"""Parsing and transformation utilities for the health module.

This module handles:
- Git version resolution
- Health status normalization
- Response construction

These are pure functions with no side effects or external dependencies.
"""

from __future__ import annotations

import subprocess
from typing import Literal

from metis.modules.health.schemas import HealthResponse


def get_git_version() -> str:
    """Get the current git commit SHA (short form).

    Returns:
        Git commit SHA (7 chars) or "unknown" if not in a git repo
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return "unknown"
    except Exception:
        return "unknown"


def normalize_status(status: str) -> Literal["ok", "down"]:
    """Normalize a status string to the canonical form.

    Args:
        status: Any status string (ok, down, healthy, unhealthy, etc.)

    Returns:
        "ok" or "down"
    """
    if status in ("ok", "healthy"):
        return "ok"
    return "down"


def build_health_response(
    db_status: str,
    redis_status: str,
    version: str,
) -> HealthResponse:
    """Build a HealthResponse from component statuses.

    Args:
        db_status: Database health status string
        redis_status: Redis health status string
        version: Application version string

    Returns:
        HealthResponse with computed overall status
    """
    db_normalized = normalize_status(db_status)
    redis_normalized = normalize_status(redis_status)

    overall_status: Literal["ok", "down"] = (
        "ok" if db_normalized == "ok" and redis_normalized == "ok" else "down"
    )

    return HealthResponse(
        status=overall_status,
        db=db_normalized,
        redis=redis_normalized,
        version=version,
    )


__all__ = [
    "build_health_response",
    "get_git_version",
    "normalize_status",
]
