"""Structured logging configuration for the Metis server.

This module provides a unified logging setup using structlog, configured once
at startup in all processes (api, worker, scheduler). Logs are JSON lines in
production and human-readable console output locally.

The logging pipeline:
1. merge_contextvars - merges context variables (request_id, run_id, etc.)
2. add_log_level - adds log level to each event
3. TimeStamper - adds ISO 8601 UTC timestamp
4. add_service_info - adds service name, env, version
5. redact_secrets - masks sensitive values in log dictionaries
6. StackInfoRenderer - adds stack info if present
7. format_exc_info - formats exception info
8. JSONRenderer or ConsoleRenderer - final output formatting

Usage:
    from metis.core.config import get_settings
    from metis.core.logging import configure_logging, get_logger

    settings = get_settings()
    configure_logging(settings)

    logger = get_logger(__name__)
    logger.info("message", key="value")
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any, cast

import structlog
from structlog.stdlib import BoundLogger, LoggerFactory

from metis.core.config import Settings

# Regex patterns for secret redaction (case-insensitive)
_SECRET_PATTERNS = [
    re.compile(r"key", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"authorization", re.IGNORECASE),
]


def _redact_secrets(_: Any, logger: Any, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Redact values under keys matching secret patterns.

    This processor is called for each log event and masks values where the
    key matches patterns like 'key', 'token', 'secret', 'password', 'authorization'.
    """
    for key in list(event_dict.keys()):
        for pattern in _SECRET_PATTERNS:
            if pattern.search(str(key)):
                event_dict[key] = "**********"
                break
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Configure structlog for the Metis server.

    This should be called once at startup in each process (api, worker, scheduler).

    Args:
        settings: The application settings containing log_level and log_json flags.
    """
    # Add service info to logs
    service_info = {
        "service": "metis",
        "env": settings.app_env,
        "version": settings.app_version,
    }

    # Build processor chain
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    # Add service info as a processor
    def add_service_info(_: Any, __: Any, event_dict: dict[str, Any]) -> dict[str, Any]:
        event_dict.update(service_info)
        return event_dict

    processors.append(add_service_info)
    processors.append(_redact_secrets)
    processors.append(structlog.processors.StackInfoRenderer())
    processors.append(structlog.processors.format_exc_info)

    # Choose renderer based on environment
    if settings.log_json:
        # JSON output for production
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Human-readable console output for development
        processors.append(structlog.dev.ConsoleRenderer())

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=BoundLogger,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to use structlog
    # Route uvicorn, sqlalchemy, arq, httpx through structlog
    system_loggers = ["uvicorn", "uvicorn.access", "sqlalchemy", "arq", "httpx"]

    for name in system_loggers:
        log = logging.getLogger(name)
        log.handlers.clear()
        log.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

        # Create a handler that uses structlog formatting
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
        log.propagate = False


def get_logger(name: str) -> BoundLogger:
    """Get a structlog BoundLogger for the given name.

    The logger is automatically bound with service info (service, env, version)
    via the configure_logging processor chain.

    Args:
        name: The logger name, typically __name__ of the calling module.

    Returns:
        A structlog BoundLogger instance.
    """
    logger = structlog.get_logger(name)
    # Cast to BoundLogger for type checking (structlog returns a lazy proxy)
    return cast(BoundLogger, logger)


def bind_context(**kwargs: Any) -> None:
    """Bind context variables to all subsequent log lines.

    Uses structlog.contextvars to attach values like request_id, run_id,
    workspace_id to all log lines in the current context.

    Args:
        **kwargs: Key-value pairs to bind to the logging context.
                  Common keys: request_id, run_id, workspace_id, idea_id
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context(**kwargs: Any) -> None:
    """Clear context variables from the logging context.

    Args:
        **kwargs: Key-value pairs to clear from the logging context.
                  If empty, clears all context variables.
    """
    if kwargs:
        structlog.contextvars.unbind_contextvars(**kwargs)
    else:
        structlog.contextvars.clear_contextvars()


__all__ = [
    "configure_logging",
    "get_logger",
    "bind_context",
    "clear_context",
]