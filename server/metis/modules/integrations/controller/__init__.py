"""HTTP routes of the integrations module (``/v1/integrations``)."""

from __future__ import annotations

from fastapi import APIRouter

from metis.modules.integrations.controller import exports, ideas, integrations

router = APIRouter(prefix="/v1", tags=["integrations"])
router.include_router(integrations.router)
router.include_router(exports.router)
router.include_router(ideas.router)

__all__ = ["router"]
