"""Integration routes: ``/v1/integrations``.

``connect`` and ``callback`` are the two halves of the OAuth round trip; the callback answers
with browser redirects, never JSON errors, and commits only on success. Thin controllers: the
work lives in ``service``.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from metis.core.config import get_settings
from metis.core.db import SessionDep
from metis.core.error_handlers import metis_error_response
from metis.core.errors import MetisError
from metis.core.redis import RedisDep
from metis.modules.auth import CurrentUserDep
from metis.modules.identity import CurrentWorkspaceDep
from metis.modules.integrations import service
from metis.modules.integrations.deps import OptionalUserDep, ProviderHttpDep
from metis.modules.integrations.dto import (
    ConnectRequest,
    ConnectStarted,
    IntegrationList,
    IntegrationProvider,
    ToolList,
)

router = APIRouter(prefix="/integrations")

SIGN_IN_PATH = "/sign-in"
FALLBACK_REDIRECT = "/?settings=integrations"


@router.get("", response_model=IntegrationList)
async def list_integrations(session: SessionDep, workspace: CurrentWorkspaceDep) -> IntegrationList:
    """Each provider's connection status in the current workspace."""
    items = await service.connections.list_integrations(session, workspace.workspace.id)
    return IntegrationList(items=items)


@router.post("/{provider}/connect", response_model=ConnectStarted)
async def connect(
    redis: RedisDep,
    make_client: ProviderHttpDep,
    workspace: CurrentWorkspaceDep,
    caller: CurrentUserDep,
    provider: IntegrationProvider,
    body: ConnectRequest,
) -> ConnectStarted:
    """Start the OAuth flow (owners only); the web sends the browser to ``authorize_url``."""
    return await service.oauth.start_connect(
        redis, make_client, workspace, caller.user, provider, body.redirect_to
    )


@router.get(
    "/{provider}/callback", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND
)
async def callback(
    session: SessionDep,
    redis: RedisDep,
    make_client: ProviderHttpDep,
    caller: OptionalUserDep,
    provider: IntegrationProvider,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Finish the OAuth flow and return to the web app. Any failure stores nothing."""
    if caller is None:
        return _redirect(SIGN_IN_PATH)
    try:
        result = await service.oauth.finish_connect(
            session, redis, make_client, caller.user, provider, code=code, state=state, error=error
        )
    except MetisError as exc:
        await session.rollback()
        return _redirect(FALLBACK_REDIRECT, integration_error=exc.code.value)
    return _redirect(result.redirect_to, integration=result.provider.value)


@router.get(
    "/{provider}/tools",
    response_model=ToolList,
    responses={status.HTTP_409_CONFLICT: {"description": "Not connected, or expired"}},
)
async def list_tools(
    request: Request,
    session: SessionDep,
    make_client: ProviderHttpDep,
    workspace: CurrentWorkspaceDep,
    provider: IntegrationProvider,
) -> ToolList | JSONResponse:
    """The tools the connected server offers. An expired connection is returned as a 409
    problem, not raised, so the ``expired`` mark still commits."""
    listing = await service.connections.list_tools(
        session, make_client, workspace.workspace.id, provider
    )
    if listing.error is not None:
        return metis_error_response(request, listing.error)
    return ToolList(items=listing.tools)


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(
    session: SessionDep,
    make_client: ProviderHttpDep,
    workspace: CurrentWorkspaceDep,
    provider: IntegrationProvider,
) -> Response:
    """Disconnect the provider (owners only)."""
    await service.connections.disconnect(session, make_client, workspace, provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _redirect(path: str, **params: str) -> RedirectResponse:
    """A redirect to the web app; ``params`` are appended to the path's own query."""
    url = get_settings().web_base_url.rstrip("/") + path
    if params:
        url += ("&" if "?" in path else "?") + urlencode(params, quote_via=quote)
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)
