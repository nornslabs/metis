"""Dependencies of the integrations routes.

The connect callback is a browser navigation: a missing or expired session must send the
browser to sign-in, not show a JSON problem, so it uses ``optional_user`` instead of
``CurrentUserDep``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from metis.core.db import SessionDep
from metis.core.errors import NotSignedInError, SessionExpiredError
from metis.core.redis import RedisDep
from metis.helpers.http import ClientFactory, provider_http_factory
from metis.modules.auth import SessionUser, current_user


async def optional_user(
    request: Request, session: SessionDep, redis: RedisDep
) -> SessionUser | None:
    """The signed-in user, or ``None`` when there is no usable session cookie."""
    try:
        return await current_user(request, session, redis)
    except (NotSignedInError, SessionExpiredError):
        return None


OptionalUserDep = Annotated[SessionUser | None, Depends(optional_user)]
ProviderHttpDep = Annotated[ClientFactory, Depends(provider_http_factory)]
