"""SQLAlchemy models for the ``identity`` schema, one file per domain.

Migrations ``0003_identity`` and ``0005_provider_keys``.

Importing this package registers every table on ``Base.metadata``.
"""

from __future__ import annotations

from metis.modules.identity.models.provider_keys import ProviderKeyRow
from metis.modules.identity.models.settings import WorkspaceSettingsRow
from metis.modules.identity.models.workspaces import MemberRow, WorkspaceRow

__all__ = ["MemberRow", "ProviderKeyRow", "WorkspaceRow", "WorkspaceSettingsRow"]
