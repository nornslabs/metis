"""Core infrastructure module.

This module contains shared infrastructure components:
- config: Global settings loaded from environment
- db: Database session management
- jobs: Arq worker configuration
- middleware: Request context middleware
- ports: Protocol definitions for external integrations
- security: Security-related utilities
- errors: Error types and error code catalog
- error_handlers: Centralized error handlers
"""

from metis.core.config import Settings, get_settings
from metis.core.errors import (
    ERROR_CATALOG,
    AuthError,
    BudgetError,
    ConflictError,
    ErrorCode,
    ErrorSpec,
    InvalidInputError,
    MetisError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UpstreamError,
)

__all__ = [
    "Settings",
    "get_settings",
    "ErrorCode",
    "ErrorSpec",
    "ERROR_CATALOG",
    "MetisError",
    "NotFoundError",
    "ConflictError",
    "AuthError",
    "PermissionDeniedError",
    "InvalidInputError",
    "UpstreamError",
    "BudgetError",
    "RateLimitError",
]