"""Test-only probe routes that depend on ``CurrentUserDep``, mounted once on the app.

Importing this module mounts ``/v1/_test/*``; Python imports it once, so every
test file that needs the probe can import it.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from metis.core import security
from metis.entrypoints.api import app
from metis.modules.identity import CurrentUserDep
from metis.modules.identity.schemas import SessionUser

PROBE = "/v1/_test/session"
COOKIE_PROBE = "/v1/_test/cookie"
PROBE_COOKIE_TOKEN = "probe-token"

_probe = APIRouter(prefix="/v1/_test")


def _who(caller: SessionUser) -> dict[str, str]:
    return {"user_id": str(caller.user.id), "session_id": str(caller.session_id)}


@_probe.get("/session")
async def _session_get(caller: CurrentUserDep) -> dict[str, str]:
    return _who(caller)


@_probe.post("/session")
async def _session_post(caller: CurrentUserDep) -> dict[str, str]:
    return _who(caller)


@_probe.post("/cookie")
async def _set_cookie(response: Response) -> None:
    security.set_session_cookie(response, PROBE_COOKIE_TOKEN)


app.include_router(_probe)
