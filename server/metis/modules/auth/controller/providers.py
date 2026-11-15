"""Sign-in provider list: ``GET /v1/auth/providers``."""

from __future__ import annotations

from fastapi import APIRouter

from metis.modules.auth.providers import GoogleProviderDep
from metis.modules.auth.providers.base import AuthProviderName

router = APIRouter(prefix="/providers")


@router.get("", response_model=list[AuthProviderName])
async def list_providers(google: GoogleProviderDep) -> list[AuthProviderName]:
    """Sign-in providers this server offers."""
    return [] if google is None else [AuthProviderName.GOOGLE]
