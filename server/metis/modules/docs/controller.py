"""HTTP routes for protected API docs (controller layer).

Serves Swagger UI, ReDoc and the OpenAPI schema, all behind ``current_user``
authentication. FastAPI's default docs URLs are disabled in
``entrypoints/api.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

from metis.modules.auth import CurrentUserDep

router = APIRouter(prefix="/v1/docs", tags=["docs"])


@router.get("", include_in_schema=False)
async def swagger_ui(caller: CurrentUserDep, request: Request):
    """Swagger UI for the Metis API (requires sign-in)."""
    return get_swagger_ui_html(
        openapi_url="/v1/docs/openapi.json",
        title="Metis API - Swagger UI",
    )


@router.get("/openapi.json", include_in_schema=False)
async def openapi_schema(caller: CurrentUserDep, request: Request) -> dict:
    """OpenAPI schema for the Metis API (requires sign-in)."""
    return get_openapi(
        title=request.app.title,
        version=request.app.version,
        description=request.app.description,
        routes=request.app.routes,
        tags=request.app.openapi_tags,
    )


@router.get("/redoc", include_in_schema=False)
async def redoc(caller: CurrentUserDep, request: Request):
    """ReDoc for the Metis API (requires sign-in)."""
    return get_redoc_html(
        openapi_url="/v1/docs/openapi.json",
        title="Metis API - ReDoc",
    )


__all__ = ["router"]
