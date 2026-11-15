"""SQLAlchemy models for the ``auth`` schema, one file per table (migrations ``0006`` to ``0009``).

Importing this package registers every table on ``Base.metadata``.
"""

from __future__ import annotations

from metis.modules.auth.models.identities import IdentityRow
from metis.modules.auth.models.sessions import SessionRow
from metis.modules.auth.models.users import UserRow

__all__ = ["IdentityRow", "SessionRow", "UserRow"]
