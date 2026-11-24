"""HTTP routes of the integrations module (``/v1/integrations``)."""

from __future__ import annotations

from fastapi import APIRouter

from metis.modules.integrations.controller import integrations

router = APIRouter(prefix="/v1", tags=["integrations"])
router.include_router(integrations.router)

__all__ = ["router"]
