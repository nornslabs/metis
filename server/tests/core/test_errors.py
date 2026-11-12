"""Tests for the global error handling system."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from metis.core.errors import (
    ErrorCode,
    ERROR_CATALOG,
    MetisError,
    NotFoundError,
    ConflictError,
    AuthError,
    PermissionDeniedError,
    InvalidInputError,
    UpstreamError,
    BudgetError,
    RateLimitError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_settings(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Create test environment variables."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres@localhost:5432/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("AUTH_JWT_SECRET", "dGVzdC1qb2tlLXNpemUgMTIzNDU2Nzg5MDEyMzQ1Ng==")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "test")
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", "f2wC_KP7gQbilJDW715g8oywAf_ZQILThi25KDsH070=")
    return {
        "DATABASE_URL": "postgresql+asyncpg://postgres@localhost:5432/test",
        "REDIS_URL": "redis://localhost:6379/0",
        "AUTH_JWT_SECRET": "dGVzdC1qb2tlLXNpemUgMTIzNDU2Nzg5MDEyMzQ1Ng==",
        "AUTH_JWT_AUDIENCE": "test",
        "ENCRYPTION_MASTER_KEY": "f2wC_KP7gQbilJDW715g8oywAf_ZQILThi25KDsH070=",
    }


# ---------------------------------------------------------------------------
# ErrorCode catalog tests
# ---------------------------------------------------------------------------


def test_every_error_code_has_catalog_entry() -> None:
    """A test asserts every ErrorCode has a catalog entry."""
    # Every ErrorCode should have a corresponding entry in ERROR_CATALOG
    for code in ErrorCode:
        assert code in ERROR_CATALOG, f"Missing catalog entry for {code}"
        spec = ERROR_CATALOG[code]
        assert spec.status > 0, f"Invalid status for {code}"
        assert spec.title, f"Missing title for {code}"


def test_catalog_entries_have_valid_fields() -> None:
    """Catalog entries should have valid status codes and titles."""
    for code, spec in ERROR_CATALOG.items():
        # Check status is valid
        assert 400 <= spec.status <= 599, f"Invalid status {spec.status} for {code}"

        # Check title is a non-empty string
        assert isinstance(spec.title, str) and spec.title, f"Missing title for {code}"

        # Check retryable is boolean
        assert isinstance(spec.retryable, bool), f"retryable must be bool for {code}"


# ---------------------------------------------------------------------------
# MetisError class tests
# ---------------------------------------------------------------------------


def test_invalid_input_error_has_status_from_catalog() -> None:
    """InvalidInputError should get status from catalog."""
    error = InvalidInputError(detail="Bad input")
    assert error.status == 422
    assert error.title == "Validation Failed"


def test_invalid_input_error_with_errors() -> None:
    """InvalidInputError can carry validation errors."""
    errors = [{"field": "email", "message": "Invalid format"}]
    error = InvalidInputError(errors=errors)
    assert error.errors == errors


def test_rate_limit_error_with_meta() -> None:
    """RateLimitError can carry metadata like retry_after."""
    error = RateLimitError(meta={"retry_after": 60})
    assert error.meta == {"retry_after": 60}
    assert error.retryable is True


# ---------------------------------------------------------------------------
# Domain error subclass tests
# ---------------------------------------------------------------------------


def test_not_found_error() -> None:
    """NotFoundError should have ROUTE_NOT_FOUND code."""
    error = NotFoundError(detail="Resource not found")
    assert error.code == ErrorCode.ROUTE_NOT_FOUND
    assert error.status == 404


def test_conflict_error() -> None:
    """ConflictError should have CONFLICT code."""
    error = ConflictError(detail="Version conflict")
    assert error.code == ErrorCode.CONFLICT
    assert error.status == 409


def test_auth_error() -> None:
    """AuthError should have UNAUTHORIZED code."""
    error = AuthError(detail="Invalid token")
    assert error.code == ErrorCode.UNAUTHORIZED
    assert error.status == 401


def test_permission_denied_error() -> None:
    """PermissionDeniedError should have FORBIDDEN code."""
    error = PermissionDeniedError(detail="No access")
    assert error.code == ErrorCode.FORBIDDEN
    assert error.status == 403


def test_invalid_input_error() -> None:
    """InvalidInputError should have VALIDATION_FAILED code."""
    error = InvalidInputError(detail="Invalid data")
    assert error.code == ErrorCode.VALIDATION_FAILED
    assert error.status == 422


def test_upstream_error() -> None:
    """UpstreamError should have UPSTREAM_ERROR code."""
    error = UpstreamError(detail="Service down")
    assert error.code == ErrorCode.UPSTREAM_ERROR
    assert error.status == 502


def test_budget_error() -> None:
    """BudgetError should have BUDGET_EXCEEDED code."""
    error = BudgetError(detail="Budget exceeded")
    assert error.code == ErrorCode.BUDGET_EXCEEDED
    assert error.status == 402


def test_rate_limit_error() -> None:
    """RateLimitError should have RATE_LIMITED code."""
    error = RateLimitError(detail="Too many requests")
    assert error.code == ErrorCode.RATE_LIMITED
    assert error.status == 429


def test_not_found_error_status_code() -> None:
    """NotFoundError should have 404 status."""
    error = NotFoundError(detail="Not found")
    assert error.status == 404
    assert ERROR_CATALOG[error.code] == ERROR_CATALOG[ErrorCode.ROUTE_NOT_FOUND]


def test_conflict_error_status_code() -> None:
    """ConflictError should have 409 status."""
    error = ConflictError(detail="Conflict")
    assert error.status == 409
    assert ERROR_CATALOG[error.code] == ERROR_CATALOG[ErrorCode.CONFLICT]


def test_auth_error_status_code() -> None:
    """AuthError should have 401 status."""
    error = AuthError(detail="Unauthorized")
    assert error.status == 401
    assert ERROR_CATALOG[error.code] == ERROR_CATALOG[ErrorCode.UNAUTHORIZED]


def test_permission_denied_error_status_code() -> None:
    """PermissionDeniedError should have 403 status."""
    error = PermissionDeniedError(detail="Forbidden")
    assert error.status == 403
    assert ERROR_CATALOG[error.code] == ERROR_CATALOG[ErrorCode.FORBIDDEN]


# ---------------------------------------------------------------------------
# Error repr tests
# ---------------------------------------------------------------------------


def test_error_repr() -> None:
    """Error repr should include code and detail."""
    error = InvalidInputError(detail="Bad input")
    repr_str = repr(error)
    assert "INVALID_INPUT_FAILED" not in repr_str  # code value
    assert "Bad input" in repr_str


# ---------------------------------------------------------------------------
# Error propagation tests
# ---------------------------------------------------------------------------


def test_error_is_exception() -> None:
    """MetisError should be a subclass of Exception."""
    error = InvalidInputError(detail="test")
    assert isinstance(error, Exception)


def test_error_can_be_raised_and_caught() -> None:
    """Error can be raised and caught normally."""
    error_raised = None
    try:
        raise InvalidInputError(detail="test detail")
    except InvalidInputError as e:
        error_raised = e

    assert error_raised is not None
    assert error_raised.detail == "test detail"
    assert error_raised.code == ErrorCode.VALIDATION_FAILED


# ---------------------------------------------------------------------------
# Integration test - basic handler registration
# ---------------------------------------------------------------------------


def test_error_handlers_module_importable() -> None:
    """Error handlers module should be importable."""
    from metis.core.error_handlers import register_error_handlers

    # Verify the function is callable
    assert callable(register_error_handlers)


def test_errors_can_be_imported_from_core() -> None:
    """All error types should be importable from core module."""
    from metis.core import (
        ErrorCode,
        MetisError,
        NotFoundError,
        ConflictError,
        AuthError,
        PermissionDeniedError,
        InvalidInputError,
        UpstreamError,
        BudgetError,
        RateLimitError,
        ERROR_CATALOG,
    )

    # Verify they are the correct types
    assert ErrorCode.ROUTE_NOT_FOUND == "common.route_not_found"
    assert ErrorCode.VALIDATION_FAILED == "common.validation_failed"

    error = NotFoundError(detail="test")
    assert isinstance(error, MetisError)


# ---------------------------------------------------------------------------
# Error code specific tests
# ---------------------------------------------------------------------------


def test_common_error_codes() -> None:
    """Common error codes should have expected values."""
    assert ErrorCode.INTERNAL_ERROR == "common.internal_error"
    assert ErrorCode.ROUTE_NOT_FOUND == "common.route_not_found"
    assert ErrorCode.METHOD_NOT_ALLOWED == "common.method_not_allowed"
    assert ErrorCode.VALIDATION_FAILED == "common.validation_failed"
    assert ErrorCode.RATE_LIMITED == "common.rate_limited"
    assert ErrorCode.TIMEOUT == "common.timeout"
    assert ErrorCode.UNAVAILABLE == "common.unavailable"
    assert ErrorCode.CONFLICT == "common.conflict"
    assert ErrorCode.BAD_REQUEST == "common.bad_request"


def test_auth_error_codes() -> None:
    """Auth error codes should have expected values."""
    assert ErrorCode.UNAUTHORIZED == "auth.unauthorized"
    assert ErrorCode.FORBIDDEN == "auth.forbidden"
    assert ErrorCode.TOKEN_EXPIRED == "auth.token_expired"
    assert ErrorCode.INVALID_CREDENTIALS == "auth.invalid_credentials"


def test_workflow_error_codes() -> None:
    """Workflow (run) error codes should have expected values."""
    assert ErrorCode.RUN_NOT_FOUND == "run.not_found"
    assert ErrorCode.RUN_ALREADY_RUNNING == "run.already_running"
    assert ErrorCode.RUN_INVALID_STATE == "run.invalid_state"
    assert ErrorCode.RUN_TIMEOUT == "run.timeout"
    assert ErrorCode.RUN_CANCELLED == "run.cancelled"