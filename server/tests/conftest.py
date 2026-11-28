"""Shared test setup: required settings must exist before ``metis`` modules import."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
import structlog

_REQUIRED_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/metis",
    "APP_DB_PASSWORD": "metis_app",
    "REDIS_URL": "redis://localhost:6379/0",
    "ENCRYPTION_MASTER_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "GOOGLE_CLIENT_ID": "metis-test.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "test-google-client-secret",
    "GOOGLE_REDIRECT_URI": "http://test/v1/auth/google/callback",
}

for _name, _value in _REQUIRED_ENV.items():
    os.environ.setdefault(_name, _value)


@pytest.fixture(autouse=True)
def _fresh_settings_after_test() -> Iterator[None]:
    """Drop cached settings after each test so a test's env overrides never leak.

    ``monkeypatch`` restores the environment, but the ``get_settings`` cache would keep
    the overridden values (e.g. a different ``DATABASE_URL``) for later tests.
    """
    yield
    from metis.core.config import get_settings  # noqa: PLC0415  (env must be set first)

    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _uncached_loggers() -> None:
    """Keep ``structlog.testing.capture_logs`` working whichever test used a logger first.

    ``configure_logging`` caches each logger on first use; a logger first used by an
    earlier test would then bypass ``capture_logs`` in a later one.
    """
    structlog.configure(cache_logger_on_first_use=False)
