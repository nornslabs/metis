"""HTTP routes of the identity module (``/v1/workspaces``, ``/v1/settings``)."""

from __future__ import annotations

from fastapi import APIRouter

from metis.modules.identity.controller import settings, workspaces

router = APIRouter(prefix="/v1", tags=["identity"])
router.include_router(workspaces.router)
router.include_router(settings.router)

__all__ = ["router"]
