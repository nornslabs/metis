"""Tests for the structured logging configuration.

Tests verify:
- JSON output has required fields (ts, level, event, logger, service, env, version)
- Secret values are properly redacted
- Context variables are properly bound and cleared
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
import structlog


def _access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:5000", "GET", path, "1.1", 302),
        exc_info=None,
    )


class TestSecretRedaction:
    """Tests for secret value redaction."""

    def test_secret_keys_are_redacted(self) -> None:
        """Values under keys matching secret patterns should be redacted."""
        # Get the redaction processor directly
        from metis.core.logging import _redact_secrets

        event_dict = {
            "event": "test",
            "key": "secret_key",
            "token": "secret_token",
            "password": "secret_password",
            "authorization": "Bearer secret",
            "normal_field": "visible_value",
        }

        result = _redact_secrets(None, None, event_dict.copy())

        assert result["key"] == "**********"
        assert result["token"] == "**********"
        assert result["password"] == "**********"
        assert result["authorization"] == "**********"
        assert result["normal_field"] == "visible_value"
        assert result["event"] == "test"

    def test_redaction_patterns_case_insensitive(self) -> None:
        """Secret patterns should match case-insensitive."""
        # Test that 'token' pattern matches both cases
        from metis.core.logging import _SECRET_PATTERNS

        # Find the token pattern
        token_pattern = None
        for pattern in _SECRET_PATTERNS:
            if "token" in str(pattern):
                token_pattern = pattern
                break

        assert token_pattern is not None
        # Should match both cases of 'token' in a string
        assert token_pattern.search("API_TOKEN") is not None
        assert token_pattern.search("api_token") is not None
        assert token_pattern.search("MY_TOKEN") is not None


class TestLoggingFunctions:
    """Tests for logging helper functions."""

    def test_bind_context_imports_successfully(self) -> None:
        """bind_context function should be importable."""
        from metis.core.logging import bind_context

        # Should not raise
        bind_context(test_key="test_value")
        structlog.contextvars.clear_contextvars()

    def test_clear_context_imports_successfully(self) -> None:
        """clear_context function should be importable."""
        from metis.core.logging import clear_context

        # Should not raise
        structlog.contextvars.bind_contextvars(test_key="test_value")
        clear_context()

    def test_clear_context_unbinds_only_named_keys(self) -> None:
        """clear_context("a") removes only key a."""
        from metis.core.logging import clear_context

        structlog.contextvars.bind_contextvars(request_id="r1", run_id="x")
        clear_context("request_id")

        assert structlog.contextvars.get_contextvars() == {"run_id": "x"}
        structlog.contextvars.clear_contextvars()

    def test_configure_logging_imports_successfully(self) -> None:
        """configure_logging function should be importable."""
        from metis.core.logging import configure_logging

        # Function exists
        assert callable(configure_logging)


class TestAccessLogQueryRedaction:
    """uvicorn's access line must never carry query strings (OAuth code/state live there)."""

    def test_query_string_is_dropped_from_the_access_line(self) -> None:
        from metis.core.logging import StripQueryFilter

        record = _access_record("/v1/auth/google/callback?code=c-123&state=s-456")

        assert StripQueryFilter().filter(record) is True
        message = record.getMessage()
        assert "/v1/auth/google/callback" in message
        assert "c-123" not in message and "s-456" not in message and "?" not in message

    def test_path_without_query_is_unchanged(self) -> None:
        from metis.core.logging import StripQueryFilter

        record = _access_record("/v1/auth/me")

        StripQueryFilter().filter(record)

        assert record.getMessage() == '127.0.0.1:5000 - "GET /v1/auth/me HTTP/1.1" 302'

    def test_configure_logging_installs_the_filter_on_uvicorn_access(self) -> None:
        from metis.core.config import get_settings
        from metis.core.logging import StripQueryFilter, configure_logging

        configure_logging(get_settings())

        access = logging.getLogger("uvicorn.access")
        assert any(isinstance(f, StripQueryFilter) for f in access.filters)


_CONFIGURED_LOGGERS = (
    "uvicorn",
    "uvicorn.access",
    "arq",
    "arq.worker",
    "sqlalchemy",
    "httpx",
    "httpcore",
)


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture(autouse=True)
def _restore_logger_state() -> Iterator[None]:
    """configure_logging rewrites global loggers; put them back after each test."""
    saved = {
        name: (
            logging.getLogger(name).handlers[:],
            logging.getLogger(name).filters[:],
            logging.getLogger(name).level,
            logging.getLogger(name).propagate,
        )
        for name in _CONFIGURED_LOGGERS
    }
    yield
    for name, (handlers, filters, level, propagate) in saved.items():
        log = logging.getLogger(name)
        log.handlers[:] = handlers
        log.filters[:] = filters
        log.setLevel(level)
        log.propagate = propagate


def _configure(level: str) -> None:
    from metis.core.config import get_settings
    from metis.core.logging import configure_logging

    configure_logging(get_settings().model_copy(update={"log_level": level}))


def _capture(logger_name: str) -> _Capture:
    """Attach a capture beside the handler configure_logging installed."""
    capture = _Capture()
    logging.getLogger(logger_name).addHandler(capture)
    return capture


class TestQuietLibraryLoggers:
    """SQL and HTTP client chatter stays out of the logs whatever LOG_LEVEL is."""

    @pytest.mark.parametrize("level", ["INFO", "DEBUG"])
    @pytest.mark.parametrize("name", ["sqlalchemy.engine.Engine", "httpx", "httpcore.http11"])
    def test_info_records_are_not_emitted(self, name: str, level: str) -> None:
        _configure(level)
        capture = _capture(name)

        logging.getLogger(name).info("SELECT 1")
        logging.getLogger(name).debug("detail")

        assert capture.messages == []

    @pytest.mark.parametrize("name", ["sqlalchemy.engine.Engine", "httpx", "httpcore.http11"])
    def test_warnings_and_errors_are_still_emitted(self, name: str) -> None:
        _configure("INFO")
        capture = _capture(name)

        logging.getLogger(name).warning("slow")
        logging.getLogger(name).error("failed")

        assert capture.messages == ["slow", "failed"]

    def test_arq_still_follows_log_level(self) -> None:
        _configure("INFO")
        capture = _capture("arq.worker")

        logging.getLogger("arq.worker").info("job started")

        assert capture.messages == ["job started"]


class TestHealthCheckAccessFilter:
    @pytest.mark.parametrize("path", ["/v1/health", "/v1/health?probe=1"])
    def test_health_access_line_is_dropped(self, path: str) -> None:
        from metis.core.logging import HealthCheckAccessFilter

        assert HealthCheckAccessFilter().filter(_access_record(path)) is False

    @pytest.mark.parametrize(
        "path", ["/v1/auth/me", "/v1/health/deep", "/v1/ideas", "/v1/ideas?q=health"]
    )
    def test_other_access_lines_are_kept(self, path: str) -> None:
        from metis.core.logging import HealthCheckAccessFilter

        assert HealthCheckAccessFilter().filter(_access_record(path)) is True

    def test_configure_logging_installs_the_filter_once(self) -> None:
        from metis.core.logging import HealthCheckAccessFilter

        _configure("INFO")
        _configure("INFO")

        access = logging.getLogger("uvicorn.access")
        assert sum(isinstance(f, HealthCheckAccessFilter) for f in access.filters) == 1

    @pytest.mark.parametrize("level", ["INFO", "DEBUG"])
    def test_access_logger_drops_health_and_keeps_other_routes(self, level: str) -> None:
        _configure(level)
        capture = _capture("uvicorn.access")
        access = logging.getLogger("uvicorn.access")
        for path in ("/v1/health", "/v1/auth/me?code=c-1"):
            access.handle(_access_record(path))

        assert len(capture.messages) == 1
        assert "/v1/auth/me" in capture.messages[0]
        assert "c-1" not in capture.messages[0]


class TestArqIdleHealthFilter:
    """arq has no switch for its idle ``recording health`` line, so it is filtered."""

    def test_idle_health_line_is_dropped_and_job_lines_are_kept(self) -> None:
        _configure("INFO")
        capture = _capture("arq.worker")
        worker = logging.getLogger("arq.worker")

        worker.info("recording health: j_complete=0 j_failed=0 j_retried=0 j_ongoing=0 queued=0")
        worker.info("  0.10s → job-1:run_graph(run_id='r1')")
        worker.info("  0.20s ← job-1:run_graph ● None")
        worker.error("  0.30s ! job-2:run_graph failed")

        assert capture.messages == [
            "  0.10s → job-1:run_graph(run_id='r1')",
            "  0.20s ← job-1:run_graph ● None",
            "  0.30s ! job-2:run_graph failed",
        ]

    def test_configure_logging_installs_the_filter_once(self) -> None:
        from metis.core.logging import ArqIdleHealthFilter

        _configure("INFO")
        _configure("INFO")

        worker = logging.getLogger("arq.worker")
        assert sum(isinstance(f, ArqIdleHealthFilter) for f in worker.filters) == 1
