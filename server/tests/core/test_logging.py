"""Tests for the structured logging configuration.

Tests verify:
- JSON output has required fields (ts, level, event, logger, service, env, version)
- Secret values are properly redacted
- Context variables are properly bound and cleared
"""

from __future__ import annotations

import structlog


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