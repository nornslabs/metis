"""Opaque list cursors for keyset pagination on ``(updated_at, id)``, latest activity first."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from uuid import UUID

from metis.core.errors import InvalidInputError

_SEPARATOR = "|"


def encode_cursor(activity_at: datetime, row_id: UUID) -> str:
    """The cursor that resumes after the row ``(activity_at, row_id)``."""
    raw = f"{activity_at.isoformat()}{_SEPARATOR}{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Parse a cursor from ``encode_cursor``; anything else is a 422."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        stamp, row_id = base64.urlsafe_b64decode(padded.encode()).decode().split(_SEPARATOR)
        activity_at = datetime.fromisoformat(stamp)
        if activity_at.tzinfo is None:
            raise ValueError("naive timestamp")
        return activity_at, UUID(row_id)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise InvalidInputError(
            "Invalid cursor", errors=[{"field": "query.cursor", "message": "Invalid cursor"}]
        ) from exc
