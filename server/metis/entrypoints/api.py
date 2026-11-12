"""FastAPI application entrypoint for the API process.

This is a minimal app so the API binds and stays up. The real ``/v1`` routes
(interviews, ideas, scoring, runs, events) are added per PRD as the modules
land. See ``server-context.md`` for the API conventions.
"""

from __future__ import annotations

import sys

from fastapi import FastAPI

from metis.core.config import get_settings
from metis.core.error_handlers import register_error_handlers
from metis.core.logging import configure_logging

# Configure logging first (before any other imports that might log)
try:
    settings = get_settings()
    configure_logging(settings)
except Exception as e:
    # Use structlog for error logging since we may not have configured it yet
    import structlog

    structlog.configure(processors=[structlog.processors.JSONRenderer()])
    logger = structlog.get_logger()
    logger.error("Configuration error", error=str(e))
    sys.exit(1)

app = FastAPI(title="Metis", version="0.1.0")

# Register centralized error handlers (application/problem+json responses)
register_error_handlers(app)

# Add request context middleware for logging with request_id
from metis.core.middleware import RequestContextMiddleware  # noqa: E402

app.add_middleware(RequestContextMiddleware)

# Include health check router (before auth-required routes)
# noqa: E402 - import after app creation to avoid circular deps
from metis.modules.health import router as health_router  # noqa: E402

app.include_router(health_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "metis", "status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("metis.entrypoints.api:app", host="0.0.0.0", port=8000)