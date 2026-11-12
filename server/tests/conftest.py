"""Shared test setup: required settings must exist before ``metis`` modules import."""

from __future__ import annotations

import os

_REQUIRED_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/metis",
    "REDIS_URL": "redis://localhost:6379/0",
    "AUTH_JWT_SECRET": "test-jwt-secret",
    "AUTH_JWT_AUDIENCE": "metis",
    "ENCRYPTION_MASTER_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
}

for _name, _value in _REQUIRED_ENV.items():
    os.environ.setdefault(_name, _value)
