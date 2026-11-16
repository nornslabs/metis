"""HTTP routes of the ideas module (``/v1/ideas``)."""

from __future__ import annotations

from fastapi import APIRouter

from metis.modules.ideas.controller import ideas

router = APIRouter(prefix="/v1", tags=["ideas"])
router.include_router(ideas.router)

__all__ = ["router"]
