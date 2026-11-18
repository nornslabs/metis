"""The Postgres schema the research tables live in, and the tables they point at."""

from __future__ import annotations

SCHEMA = "research"

# Owned by other modules; the FK targets are named here, never imported.
WORKSPACES_TABLE = "identity.workspaces"
IDEAS_TABLE = "ideas.ideas"
RUNS_TABLE = "ideas.workflow_runs"
