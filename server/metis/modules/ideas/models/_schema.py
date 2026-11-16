"""The Postgres schema the ideas tables live in, and the tables they point at."""

from __future__ import annotations

SCHEMA = "ideas"

# Owned by other modules; the FK targets are named here, never imported.
WORKSPACES_TABLE = "identity.workspaces"
USERS_TABLE = "auth.users"
