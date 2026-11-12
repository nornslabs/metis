"""FastAPI middleware for request context propagation.

This module provides middleware that:
1. Reads or generates a request ID from X-Request-ID header
2. Binds the request_id to structlog context
3. Adds X-Request-ID to response headers
4. Clears context after request completion
5. Logs request access at appropriate level

Usage:
    from fastapi import FastAPI
    from metis.core.middleware import RequestContextMiddleware

    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from metis.core.logging import bind_context, clear_context, get_logger

__all__ = ["RequestContextMiddleware"]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware that manages request context for structured logging.

    This middleware:
    1. Reads X-Request-ID header or generates a UUID if not present
    2. Binds request_id to structlog context variables
    3. Adds X-Request-ID to response headers
    4. Writes access log line at the end of request processing
    5. Clears context after response is sent
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request with context management and logging."""
        logger = get_logger(__name__)

        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Bind request_id to context
        bind_context(request_id=request_id)

        # Record start time
        start_time = time.perf_counter()

        # Process the request first
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Get response details
        path = request.url.path
        method = request.method
        status = response.status_code

        # Determine log level (DEBUG for health checks, INFO otherwise)
        if path == "/v1/health" and method == "GET":
            # Health check logged at DEBUG level
            logger.debug(
                "http.request",
                method=method,
                path=path,
                status=status,
                duration_ms=round(duration_ms, 2),
                request_id=request_id,
            )
        else:
            # Regular request logged at INFO level
            logger.info(
                "http.request",
                method=method,
                path=path,
                status=status,
                duration_ms=round(duration_ms, 2),
                request_id=request_id,
            )

        # Add X-Request-ID to response headers
        headers = response.headers
        headers["X-Request-ID"] = request_id

        # Clear context
        clear_context(request_id=True)

        return response