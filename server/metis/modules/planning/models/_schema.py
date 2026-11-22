"""The Postgres schema the planning tables live in, and the tables they point at."""

from __future__ import annotations

SCHEMA = "planning"

# Owned by other modules; the FK targets are named here, never imported.
WORKSPACES_TABLE = "identity.workspaces"
IDEAS_TABLE = "ideas.ideas"
SPEC_VERSIONS_TABLE = "ideas.spec_versions"
