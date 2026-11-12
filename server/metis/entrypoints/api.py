"""FastAPI application entrypoint for the API process.

This is a minimal app so the API binds and stays up. The real ``/v1`` routes
(interviews, ideas, scoring, runs, events) are added per PRD as the modules
land. See ``server-context.md`` for the API conventions.
"""

import sys

from fastapi import FastAPI

from metis.core.config import get_settings
from metis.core.error_handlers import register_error_handlers

# Validate settings at import time - this will raise ValidationError if
# required fields are missing and exit with a clear message
try:
    settings = get_settings()
except Exception as e:
    print(f"Configuration error: {e}", file=sys.stderr)
    sys.exit(1)

app = FastAPI(title="Metis", version="0.1.0")

# Register centralized error handlers (application/problem+json responses)
register_error_handlers(app)

# Include health check router (first route, before auth-required routes)
# noqa: E402 - import after app creation to avoid circular deps
from metis.modules.health import router as health_router  # noqa: E402

app.include_router(health_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "metis", "status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("metis.entrypoints.api:app", host="0.0.0.0", port=8000)