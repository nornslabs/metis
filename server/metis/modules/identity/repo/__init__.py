"""Postgres access for the identity module, one file per table.

Call it domain-qualified: ``repo.workspaces.create(...)``.
"""

from __future__ import annotations

from metis.modules.identity.repo import members, provider_keys, rls, settings, workspaces

__all__ = ["members", "provider_keys", "rls", "settings", "workspaces"]
