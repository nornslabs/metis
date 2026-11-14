"""Identity module: users, sessions, workspaces, membership, provider keys and settings.

Use only what is exported here.
"""

from metis.modules.identity.api import router
from metis.modules.identity.auth_api import router as auth_router
from metis.modules.identity.auth_deps import SessionUserDep, session_user
from metis.modules.identity.deps import (
    CurrentUser,
    CurrentUserDep,
    CurrentWorkspaceDep,
    current_user,
    current_workspace,
)
from metis.modules.identity.schemas import (
    MemberRole,
    Membership,
    ProviderCredentials,
    ProviderKind,
    SessionUser,
    User,
    Workspace,
)
from metis.modules.identity.service import (
    add_member,
    create_workspace,
    ensure_personal_workspace,
    get_key_for_use,
    list_workspaces,
    upsert_user_from_claims,
)

__all__ = [
    "SessionUser",
    "SessionUserDep",
    "session_user",
    "CurrentUser",
    "CurrentUserDep",
    "CurrentWorkspaceDep",
    "current_user",
    "current_workspace",
    "router",
    "auth_router",
    "MemberRole",
    "Membership",
    "ProviderCredentials",
    "ProviderKind",
    "User",
    "Workspace",
    "add_member",
    "create_workspace",
    "ensure_personal_workspace",
    "get_key_for_use",
    "list_workspaces",
    "upsert_user_from_claims",
]
