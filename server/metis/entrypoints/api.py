"""FastAPI application entrypoint for the API process.

``create_app()`` builds the app; the module-level ``app`` is what uvicorn
serves (``metis.entrypoints.api:app``). ``/v1/health`` and ``/v1/auth/*``
(sign-in, sign-out) are public; every other ``/v1`` route depends on
``current_user`` or ``current_workspace`` (session cookie + workspace scoping).
Module routers are added per PRD as the modules land. See
``server-context.md`` for the API conventions.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from metis.core.config import Settings, get_settings
from metis.core.error_handlers import register_error_handlers
from metis.core.logging import configure_logging
from metis.core.middleware import RequestContextMiddleware
from metis.core.redis import close_redis
from metis.modules.auth import router as auth_router
from metis.modules.docs import router as docs_router
from metis.modules.health import router as health_router
from metis.modules.ideas import router as ideas_router
from metis.modules.identity import router as identity_router
from metis.modules.research import router as research_router
from metis.modules.scoring import router as scoring_router

CORS_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_HEADERS = [
    "Content-Type",
    "X-Workspace-Id",
    "Idempotency-Key",
    "X-Request-ID",
    "X-Metis-Client",
]

OPENAPI_DESCRIPTION = """Metis HTTP API.

Protected endpoints use the configured session cookie set by the Google
sign-in flow. In Swagger UI, sign in to Metis in the same browser first or
authorize with the session cookie. Workspace-scoped endpoints accept the
`X-Workspace-Id` header; omit it to use the personal workspace. Mutating
requests also require `X-Metis-Client: web`.
"""

OPENAPI_TAGS = [
    {"name": "health", "description": "Service liveness and readiness."},
    {"name": "auth", "description": "Sign-in, session, and authentication provider operations."},
    {"name": "identity", "description": "User settings and workspace membership."},
    {"name": "ideas", "description": "Ideas and their workflow runs."},
    {"name": "research", "description": "Research snapshots and findings."},
]


def _load_settings() -> Settings:
    """Load settings and configure logging, or log the error and exit."""
    try:
        settings = get_settings()
        configure_logging(settings)
    except Exception as e:
        # Logging may not be configured yet: emit one plain JSON line, then stop.
        structlog.configure(processors=[structlog.processors.JSONRenderer()])
        structlog.get_logger().error("Configuration error", error=str(e))
        sys.exit(1)
    return settings


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    yield
    await close_redis()


def _add_middleware(app: FastAPI, settings: Settings) -> None:
    # Request context (request_id in logs and problem bodies) for every request.
    app.add_middleware(RequestContextMiddleware)
    # CORS for the explicit web origins only (never "*"): credentials allowed so
    # the browser sends the session cookie. Added last so it is the outermost
    # middleware and answers preflights directly.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins(),
        allow_credentials=True,
        allow_methods=CORS_METHODS,
        allow_headers=CORS_HEADERS,
        expose_headers=["X-Request-ID"],
    )


def _include_routers(app: FastAPI) -> None:
    # Public: liveness/readiness for compose, CI and deploy probes.
    app.include_router(health_router)
    # Public sign-in / sign-out (redirects and the session cookie).
    app.include_router(auth_router)
    # Every other /v1 route requires a session cookie via current_user / current_workspace.
    app.include_router(identity_router)
    app.include_router(ideas_router)
    app.include_router(research_router)
    app.include_router(scoring_router)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API app: error handlers, middleware and routers."""
    settings = settings or _load_settings()
    app = FastAPI(
        title="Metis API",
        summary="HTTP API for Metis",
        description=OPENAPI_DESCRIPTION,
        version=settings.app_version,
        openapi_tags=OPENAPI_TAGS,
        lifespan=_lifespan,
        # Docs are served under /v1/docs/* with session auth (see docs module).
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    register_error_handlers(app)
    _add_middleware(app, settings)
    _include_routers(app)
    app.include_router(docs_router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"service": "metis", "status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("metis.entrypoints.api:app", host="0.0.0.0", port=8000)
