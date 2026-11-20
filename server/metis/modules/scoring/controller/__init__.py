"""HTTP routes of the scoring module (``/v1/ideas/{id}/scores``, ``/v1/scores``)."""

from __future__ import annotations

from fastapi import APIRouter

from metis.modules.scoring.controller.ideas import router as ideas_router
from metis.modules.scoring.controller.scores import router as scores_router

router = APIRouter(prefix="/v1", tags=["scoring"])
router.include_router(ideas_router)
router.include_router(scores_router)

__all__ = ["router"]
