"""Auth module: who you are. Users, sessions, sign-in identities, OAuth and providers.

Use only what is exported here. Auth imports no other module.
"""

from metis.modules.auth.api import router
from metis.modules.auth.deps import CurrentUserDep, check_csrf, current_user
from metis.modules.auth.schemas import SessionUser, User
from metis.modules.auth.service import find_user_by_email, get_user

__all__ = [
    "CurrentUserDep",
    "SessionUser",
    "User",
    "check_csrf",
    "current_user",
    "find_user_by_email",
    "get_user",
    "router",
]
