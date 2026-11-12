"""Pydantic schemas for the health module.

This module contains only data structures - no business logic or HTTP code.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: Literal["ok", "down"]
    db: str
    redis: str
    version: str


class HealthStatus:
    """Health status values for individual components."""

    OK = "ok"
    DOWN = "down"