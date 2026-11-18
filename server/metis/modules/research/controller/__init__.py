"""HTTP routes of the research module (``/v1/ideas/{id}/research``, ``/v1/research``)."""

from __future__ import annotations

from fastapi import APIRouter

from metis.modules.research.controller.ideas import router as ideas_router
from metis.modules.research.controller.snapshots import router as snapshots_router

router = APIRouter(prefix="/v1", tags=["research"])
router.include_router(ideas_router)
router.include_router(snapshots_router)

__all__ = ["router"]
