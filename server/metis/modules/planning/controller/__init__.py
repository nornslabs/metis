"""HTTP routes of the planning module."""

from __future__ import annotations

from fastapi import APIRouter

from metis.modules.planning.controller.plans import idea_router
from metis.modules.planning.controller.plans import router as plans_router

router = APIRouter(prefix="/v1", tags=["planning"])
router.include_router(idea_router)
router.include_router(plans_router)

__all__ = ["router"]
