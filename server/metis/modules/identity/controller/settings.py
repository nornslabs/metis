"""Settings routes: ``/v1/settings`` and the BYO provider keys under ``/v1/settings/keys``.

Thin controllers: auth comes from the dependencies, work from ``service.settings`` and
``service.provider_keys``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from metis.core.db import SessionDep
from metis.core.error_handlers import metis_error_response
from metis.helpers.http import ClientFactory, provider_http_factory
from metis.modules.identity import service
from metis.modules.identity.deps import CurrentWorkspaceDep
from metis.modules.identity.dto import (
    ProviderKeyView,
    ProviderKind,
    PutProviderKeyRequest,
    SettingsPatch,
    SettingsResponse,
    WorkspaceSettingsView,
)

router = APIRouter(prefix="/settings")


ProviderHttpDep = Annotated[ClientFactory, Depends(provider_http_factory)]


@router.get("", response_model=SettingsResponse)
async def get_settings(session: SessionDep, workspace: CurrentWorkspaceDep) -> SettingsResponse:
    """Masked provider keys and run settings of the current workspace."""
    return await service.settings.get_settings_overview(session, workspace.workspace.id)


@router.patch("", response_model=WorkspaceSettingsView)
async def update_settings(
    session: SessionDep, workspace: CurrentWorkspaceDep, body: SettingsPatch
) -> WorkspaceSettingsView:
    """Change run settings; ``version`` must match the one read (409 otherwise)."""
    return await service.settings.update_settings(session, workspace, body)


@router.put("/keys/{kind}", response_model=ProviderKeyView)
async def put_provider_key(
    session: SessionDep,
    workspace: CurrentWorkspaceDep,
    kind: ProviderKind,
    body: PutProviderKeyRequest,
) -> ProviderKeyView:
    """Save or replace the workspace's key of ``kind``; the response is masked."""
    return await service.provider_keys.set_key(
        session, workspace, kind, body.value, body.base_url, body.model
    )


@router.delete("/keys/{kind}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider_key(
    session: SessionDep, workspace: CurrentWorkspaceDep, kind: ProviderKind
) -> Response:
    """Remove the workspace's key of ``kind``."""
    await service.provider_keys.delete_key(session, workspace, kind)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/keys/{kind}/test",
    response_model=ProviderKeyView,
    responses={status.HTTP_502_BAD_GATEWAY: {"description": "The provider call failed"}},
)
async def test_provider_key(
    request: Request,
    session: SessionDep,
    workspace: CurrentWorkspaceDep,
    kind: ProviderKind,
    make_client: ProviderHttpDep,
) -> ProviderKeyView | JSONResponse:
    """Check the saved key with one cheap provider call and record the result.

    A failure is returned as a 502 problem, not raised, so the request session
    still commits the recorded result.
    """
    result = await service.provider_keys.test_key(
        session, workspace.workspace.id, kind, make_client
    )
    if result.error is not None:
        return metis_error_response(request, result.error)
    return result.key
