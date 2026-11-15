"""Clock helpers."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """The current time, timezone-aware in UTC."""
    return datetime.now(tz=UTC)
