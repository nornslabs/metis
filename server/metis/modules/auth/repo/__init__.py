"""Postgres access for the auth module, one file per table.

Call it domain-qualified: ``repo.sessions.create(...)``.
"""

from __future__ import annotations

from metis.modules.auth.repo import identities, sessions, users

__all__ = ["identities", "sessions", "users"]
