"""The timezone-aware clock in ``metis.helpers.time``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from metis.helpers.time import utcnow


def test_utcnow_is_timezone_aware_utc() -> None:
    assert utcnow().utcoffset() == timedelta(0)


def test_utcnow_returns_the_current_time() -> None:
    before = datetime.now(UTC)
    now = utcnow()
    after = datetime.now(UTC)

    assert before <= now <= after
