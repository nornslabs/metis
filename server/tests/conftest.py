"""Shared test setup: required settings must exist before ``metis`` modules import."""

from __future__ import annotations

import os

_REQUIRED_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/metis",
    "REDIS_URL": "redis://localhost:6379/0",
    "ENCRYPTION_MASTER_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "GOOGLE_CLIENT_ID": "metis-test.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "test-google-client-secret",
    "GOOGLE_REDIRECT_URI": "http://test/v1/auth/google/callback",
}

for _name, _value in _REQUIRED_ENV.items():
    os.environ.setdefault(_name, _value)
