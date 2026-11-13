"""Tests for the UUIDv7 generator in ``metis.core.ids``."""

from __future__ import annotations

import time

from metis.core.ids import uuid7

UUID7_VERSION = 7
RFC_9562_VARIANT = "specified in RFC 4122"
MS_SPACING_SECONDS = 0.002
SAMPLE_SIZE = 1000


def test_uuid7_has_version_7_and_rfc_variant() -> None:
    value = uuid7()

    assert value.version == UUID7_VERSION
    assert value.variant == RFC_9562_VARIANT


def test_uuid7_embeds_current_unix_milliseconds() -> None:
    before = time.time_ns() // 1_000_000
    value = uuid7()
    after = time.time_ns() // 1_000_000

    assert before <= value.int >> 80 <= after


def test_uuid7_ids_from_later_milliseconds_sort_later() -> None:
    ids = []
    for _ in range(5):
        ids.append(uuid7())
        time.sleep(MS_SPACING_SECONDS)

    assert ids == sorted(ids)


def test_uuid7_ids_are_unique() -> None:
    assert len({uuid7() for _ in range(SAMPLE_SIZE)}) == SAMPLE_SIZE
