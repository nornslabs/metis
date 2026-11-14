"""Identity module: users, workspaces and membership. Use only what is exported here."""

from metis.modules.identity.api import router
from metis.modules.identity.deps import (
    CurrentUser,
    CurrentUserDep,
    CurrentWorkspaceDep,
    current_user,
    current_workspace,
)
from metis.modules.identity.schemas import MemberRole, Membership, User, Workspace
from metis.modules.identity.service import (
    add_member,
    create_workspace,
    ensure_personal_workspace,
    list_workspaces,
    upsert_user_from_claims,
)

__all__ = [
    "CurrentUser",
    "CurrentUserDep",
    "CurrentWorkspaceDep",
    "current_user",
    "current_workspace",
    "router",
    "MemberRole",
    "Membership",
    "User",
    "Workspace",
    "add_member",
    "create_workspace",
    "ensure_personal_workspace",
    "list_workspaces",
    "upsert_user_from_claims",
]
