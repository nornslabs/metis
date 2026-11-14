"""FastAPI application entrypoint for the API process.

``create_app()`` builds the app; the module-level ``app`` is what uvicorn
serves (``metis.entrypoints.api:app``). ``/v1/health`` is public; every other
``/v1`` route depends on ``current_user`` or ``current_workspace`` (JWT auth +
workspace scoping). Module routers are added per PRD as the modules land. See
``server-context.md`` for the API conventions.
"""

from __future__ import annotations

import sys

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from metis.core.config import Settings, get_settings
from metis.core.error_handlers import register_error_handlers
from metis.core.logging import configure_logging
from metis.core.middleware import RequestContextMiddleware
from metis.modules.health import router as health_router
from metis.modules.identity import router as identity_router

CORS_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Workspace-Id",
    "Idempotency-Key",
    "X-Request-ID",
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


def _add_middleware(app: FastAPI, settings: Settings) -> None:
    # Request context (request_id in logs and problem bodies) for every request.
    app.add_middleware(RequestContextMiddleware)
    # CORS for the web origins only. Bearer tokens, no cookies: no credentials.
    # Added last so it is the outermost middleware and answers preflights directly.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins(),
        allow_credentials=False,
        allow_methods=CORS_METHODS,
        allow_headers=CORS_HEADERS,
        expose_headers=["X-Request-ID"],
    )


def _include_routers(app: FastAPI) -> None:
    # Public: liveness/readiness for compose, CI and deploy probes.
    app.include_router(health_router)
    # Every other /v1 route requires a valid JWT via current_user / current_workspace.
    app.include_router(identity_router)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API app: error handlers, middleware and routers."""
    settings = settings or _load_settings()
    app = FastAPI(title="Metis", version=settings.app_version)
    register_error_handlers(app)
    _add_middleware(app, settings)
    _include_routers(app)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"service": "metis", "status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("metis.entrypoints.api:app", host="0.0.0.0", port=8000)
