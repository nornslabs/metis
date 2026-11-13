"""Id generation.

Python 3.12 has no ``uuid.uuid7`` and Postgres 16 has no ``uuidv7()``, so
UUIDv7 ids (RFC 9562) are generated here.
"""

from __future__ import annotations

import secrets
import time
from uuid import UUID

_TIMESTAMP_MASK = (1 << 48) - 1
_VERSION = 0x7
_VARIANT = 0b10
_RAND_A_BITS = 12
_RAND_B_BITS = 62


def uuid7() -> UUID:
    """Return a UUIDv7: 48-bit Unix ms timestamp, then random bits.

    Ids from later milliseconds sort after earlier ones; ids within the same
    millisecond are random relative to each other.
    """
    unix_ms = time.time_ns() // 1_000_000
    value = (
        (unix_ms & _TIMESTAMP_MASK) << 80
        | _VERSION << 76
        | secrets.randbits(_RAND_A_BITS) << 64
        | _VARIANT << 62
        | secrets.randbits(_RAND_B_BITS)
    )
    return UUID(int=value)
