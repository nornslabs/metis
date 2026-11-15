"""The Postgres schema of identity tables, and the auth table they point at."""

from __future__ import annotations

SCHEMA = "identity"
# ``users`` belongs to the auth module; its FK target is named here, never imported.
USERS_TABLE = "auth.users"
