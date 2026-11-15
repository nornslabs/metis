"""Auth business rules, one file per domain.

Call them domain-qualified, e.g. ``service.sessions.create_session``. Postgres goes through
``repo`` and Redis through ``cache``; services never call either store directly.
"""

from __future__ import annotations

from metis.modules.auth.service import identities, oauth, sessions, users

__all__ = ["identities", "oauth", "sessions", "users"]
