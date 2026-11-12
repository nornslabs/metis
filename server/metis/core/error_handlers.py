"""Centralized error handlers for the Metis API.

This module provides a single place to register error handlers for the FastAPI app.
All errors return a consistent `application/problem+json` response format.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from metis.core.errors import (
    ERROR_CATALOG,
    ErrorCode,
    MetisError,
)

# HTTP status codes for error handlers
_HTTP_NOT_FOUND = 404
_HTTP_METHOD_NOT_ALLOWED = 405
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403

# HTTP status code ranges for logging
_CLIENT_ERROR_MIN = 400
_CLIENT_ERROR_MAX = 499
_SERVER_ERROR_MIN = 500

logger = structlog.get_logger(__name__)


def _get_request_id(request: Request) -> str | None:
    """Get request_id from state or contextvars."""
    return getattr(request.state, "request_id", None)


def _log_error(
    log_level: str,
    request: Request,
    code: ErrorCode,
    detail: str | None,
) -> None:
    """Log an error with the appropriate level."""
    logger.log(
        log_level,
        "error_response",
        method=request.method,
        path=request.url.path,
        code=code,
        detail=detail,
    )


def _build_problem_response(
    *,
    request: Request,
    code: ErrorCode,
    detail: str | None = None,
    errors: list[dict[str, Any]] | Sequence[dict[str, Any]] | None = None,
    meta: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build a standardized problem+json response."""
    request_id = _get_request_id(request)

    error_spec = ERROR_CATALOG[code]

    body: dict[str, Any] = {
        "type": f"https://metis.ai/errors/{code}",
        "title": error_spec.title,
        "status": error_spec.status,
        "code": code,
        "detail": detail or error_spec.title,
        "request_id": request_id,
        "retryable": error_spec.retryable,
    }

    if errors:
        body["errors"] = errors
    if meta:
        body["meta"] = meta

    headers: dict[str, str] = {"Content-Type": "application/problem+json"}

    if meta and "retry_after" in meta:
        headers["Retry-After"] = str(meta["retry_after"])

    return JSONResponse(body, status_code=error_spec.status, headers=headers)


async def _handle_metis_error(request: Request, exc: MetisError) -> JSONResponse:
    """Handle MetisError exceptions."""
    status = exc.status
    if _CLIENT_ERROR_MIN <= status < _CLIENT_ERROR_MAX:
        level = "info"
    elif status >= _SERVER_ERROR_MIN:
        level = "error"
    else:
        level = "warning"

    _log_error(
        log_level=level,
        request=request,
        code=exc.code,
        detail=exc.detail,
    )
    return _build_problem_response(
        request=request,
        code=exc.code,
        detail=exc.detail,
        errors=exc.errors,
        meta=exc.meta,
    )


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle FastAPI validation errors (Pydantic and Starlette)."""
    raw_errors = exc.errors()
    errors: list[dict[str, Any]] = list(raw_errors)

    detail = "One or more fields failed validation"
    if len(errors) == 1:
        first_error = errors[0]
        loc_parts = [str(loc) for loc in first_error.get("loc", [])]
        loc = ".".join(loc_parts)
        msg = first_error.get("msg", "Validation failed")
        detail = f"{loc}: {msg}" if loc else msg

    formatted_errors: list[dict[str, Any]] = []
    for err in errors:
        loc_parts = [str(loc) for loc in err.get("loc", [])]
        formatted_errors.append({
            "field": ".".join(loc_parts),
            "message": err.get("msg"),
        })

    logger.info(
        "validation_error",
        method=request.method,
        path=request.url.path,
        errors=formatted_errors,
    )

    return _build_problem_response(
        request=request,
        code=ErrorCode.VALIDATION_FAILED,
        detail=detail,
        errors=formatted_errors,
    )


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle Starlette HTTP exceptions (404 Not Found, 405 Method Not Allowed)."""
    # Map status codes to error codes
    if exc.status_code == _HTTP_NOT_FOUND:
        code = ErrorCode.ROUTE_NOT_FOUND
        detail = "Not Found"
    elif exc.status_code == _HTTP_METHOD_NOT_ALLOWED:
        code = ErrorCode.METHOD_NOT_ALLOWED
        detail = "Method Not Allowed"
    elif exc.status_code == _HTTP_UNAUTHORIZED:
        code = ErrorCode.UNAUTHORIZED
        detail = str(exc.detail) if exc.detail else "Unauthorized"
    elif exc.status_code == _HTTP_FORBIDDEN:
        code = ErrorCode.FORBIDDEN
        detail = str(exc.detail) if exc.detail else "Forbidden"
    else:
        code = ErrorCode.BAD_REQUEST
        detail = str(exc.detail) if exc.detail else "Bad Request"

    logger.info(
        "http_exception",
        method=request.method,
        path=request.url.path,
        status=exc.status_code,
        code=code,
    )

    return _build_problem_response(
        request=request,
        code=code,
        detail=detail,
    )


async def _handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions.

    Logs the full stack trace at ERROR level but returns a generic
    `common.internal_error` response to the client.
    """
    request_id = _get_request_id(request)

    # Log with stack at ERROR level
    logger.error(
        "unhandled_exception",
        request_id=request_id,
        exc_type=type(exc).__name__,
        exc_msg=str(exc),
    )

    return _build_problem_response(
        request=request,
        code=ErrorCode.INTERNAL_ERROR,
        detail=None,  # Generic message from catalog
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register error handlers on a FastAPI app.

    Order matters - handlers are matched in order of registration specificity.
    This must be called after adding RequestContextMiddleware so that
    request IDs are available in the response.
    """
    # Handle MetisError exceptions (our domain errors)
    app.add_exception_handler(MetisError, _handle_metis_error)  # type: ignore[arg-type]

    # Handle FastAPI validation errors (Pydantic validation)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]

    # Handle Starlette HTTP exceptions (404, 405, etc.)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]

    # Handle all other unhandled exceptions
    app.add_exception_handler(Exception, _handle_unhandled_exception)


__all__ = ["register_error_handlers"]