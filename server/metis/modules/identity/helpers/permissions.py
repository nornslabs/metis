"""Permission checks shared by the identity services."""

from __future__ import annotations

from metis.core.errors import PermissionDeniedError
from metis.modules.identity.dto import MemberRole, Membership


def require_owner(membership: Membership, action: str) -> None:
    if membership.role is not MemberRole.OWNER:
        raise PermissionDeniedError(f"Only workspace owners can {action}")
