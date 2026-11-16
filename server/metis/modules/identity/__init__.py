"""Identity module: where you work. Workspaces, membership, provider keys and settings.

Users, sessions and sign-in live in ``metis.modules.auth``. Use only what is
exported here.
"""

from metis.modules.identity.controller import router
from metis.modules.identity.deps import CurrentWorkspaceDep, current_workspace
from metis.modules.identity.dto import (
    MemberRole,
    Membership,
    ProviderCredentials,
    ProviderKind,
    Workspace,
)
from metis.modules.identity.service.members import add_member
from metis.modules.identity.service.provider_keys import get_key_for_use
from metis.modules.identity.service.settings import get_settings_overview
from metis.modules.identity.service.workspaces import (
    create_workspace,
    ensure_personal_workspace,
    list_workspaces,
)

__all__ = [
    "CurrentWorkspaceDep",
    "current_workspace",
    "router",
    "MemberRole",
    "Membership",
    "ProviderCredentials",
    "ProviderKind",
    "Workspace",
    "add_member",
    "create_workspace",
    "ensure_personal_workspace",
    "get_key_for_use",
    "get_settings_overview",
    "list_workspaces",
]
