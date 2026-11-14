"""Identity module: users, workspaces and membership. Use only what is exported here."""

from metis.modules.identity.schemas import MemberRole, Membership, User, Workspace
from metis.modules.identity.service import (
    add_member,
    create_workspace,
    ensure_personal_workspace,
    list_workspaces,
    upsert_user_from_claims,
)

__all__ = [
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
