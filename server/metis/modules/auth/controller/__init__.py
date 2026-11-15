"""HTTP routes of the auth module (``/v1/auth/*``), one file per domain."""

from __future__ import annotations

from fastapi import APIRouter

from metis.modules.auth.controller import google, providers, sessions

router = APIRouter(prefix="/v1/auth", tags=["auth"])
router.include_router(providers.router)
router.include_router(google.router)
router.include_router(sessions.router)

__all__ = ["router"]
