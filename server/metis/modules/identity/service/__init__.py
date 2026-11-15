"""Identity business rules, one file per domain.

Call them domain-qualified, e.g. ``service.workspaces.get_current_workspace``.
"""

from __future__ import annotations

from metis.modules.identity.service import members, provider_keys, settings, workspaces

__all__ = ["members", "provider_keys", "settings", "workspaces"]
