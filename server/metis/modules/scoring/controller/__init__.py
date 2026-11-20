"""HTTP routes of the scoring module: scores and suggestions."""

from __future__ import annotations

from fastapi import APIRouter

from metis.modules.scoring.controller.ideas import router as ideas_router
from metis.modules.scoring.controller.scores import router as scores_router
from metis.modules.scoring.controller.suggestions import idea_router as idea_suggestions_router
from metis.modules.scoring.controller.suggestions import router as suggestions_router

router = APIRouter(prefix="/v1", tags=["scoring"])
router.include_router(ideas_router)
router.include_router(scores_router)
router.include_router(idea_suggestions_router)
router.include_router(suggestions_router)

__all__ = ["router"]
