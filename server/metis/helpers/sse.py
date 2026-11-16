"""Server-Sent Events plumbing: frame formatting and stream-id validation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from metis.core.errors import InvalidInputError

RETRY_MS = 3000
RETRY_FRAME = f"retry: {RETRY_MS}\n\n"
PING_FRAME = ": ping\n\n"
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}

_STREAM_ID = re.compile(r"^\d+(-\d+)?$")


def format_frame(event: str, data: str, event_id: str | None = None) -> str:
    """One SSE frame; ``data`` must be a single line (compact JSON)."""
    id_line = f"id: {event_id}\n" if event_id is not None else ""
    return f"{id_line}event: {event}\ndata: {data}\n\n"


def json_frame(event: str, payload: Mapping[str, Any], event_id: str | None = None) -> str:
    """A frame whose ``data`` is ``payload`` as compact JSON."""
    return format_frame(event, json.dumps(payload, separators=(",", ":"), default=str), event_id)


def parse_stream_id(raw: str, *, field: str) -> str:
    """``raw`` if it is a Redis stream id (``<ms>`` or ``<ms>-<seq>``); anything else is a 422."""
    if not _STREAM_ID.fullmatch(raw):
        raise InvalidInputError(
            "Invalid event id", errors=[{"field": field, "message": "Not a stream event id"}]
        )
    return raw
