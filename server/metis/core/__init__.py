"""Core infrastructure module.

This module contains shared infrastructure components:
- config: Global settings loaded from environment
- db: Database session management
- models: SQLAlchemy Base with naming conventions and TenantMixin
- jobs: Arq worker configuration
- middleware: Request context middleware
- ports: Protocol definitions for external integrations
- security: Security-related utilities
- errors: Error types and error code catalog
- error_handlers: Centralized error handlers
- logging: Structured logging configuration
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
from metis.core.logging import bind_context, clear_context, configure_logging, get_logger

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
    # Logging exports
    "configure_logging",
    "get_logger",
    "bind_context",
    "clear_context",
]