"""Identity module: where you work. Workspaces, membership, provider keys and settings.

Users, sessions and sign-in live in ``metis.modules.auth``. Use only what is
exported here.
"""

from metis.modules.identity.api import router
from metis.modules.identity.deps import CurrentWorkspaceDep, current_workspace
from metis.modules.identity.schemas import (
    MemberRole,
    Membership,
    ProviderCredentials,
    ProviderKind,
    Workspace,
)
from metis.modules.identity.service import (
    add_member,
    create_workspace,
    ensure_personal_workspace,
    get_key_for_use,
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
    "list_workspaces",
]
