"""HTTP routes of the ideas module (``/v1/ideas``, ``/v1/runs``)."""

from __future__ import annotations

from fastapi import APIRouter

from metis.modules.ideas.controller.ideas import router as ideas_router
from metis.modules.ideas.controller.run_events import router as run_events_router
from metis.modules.ideas.controller.runs import router as runs_router
from metis.modules.ideas.controller.specs import router as specs_router

router = APIRouter(prefix="/v1", tags=["ideas"])
router.include_router(ideas_router)
router.include_router(runs_router)
router.include_router(specs_router)
router.include_router(run_events_router)

__all__ = ["router"]
