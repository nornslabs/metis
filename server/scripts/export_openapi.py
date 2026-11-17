"""Print the API's OpenAPI schema as JSON, without running any service.

Used by the web's `npm run gen:api` and the CI drift check. The schema does not
depend on configuration, so fixed placeholder settings are used: nothing here
reads a `.env` file, connects to a database or Redis, or needs real secrets.

    uv run python scripts/export_openapi.py > openapi.json
"""

from __future__ import annotations

import json
import os
import sys

# 32 zero bytes, urlsafe base64: a valid placeholder master key, never a real one.
PLACEHOLDER_SETTINGS = {
    "APP_ENV": "development",
    "DATABASE_URL": "postgresql+asyncpg://placeholder:placeholder@localhost:5432/placeholder",
    "REDIS_URL": "redis://localhost:6379/0",
    "ENCRYPTION_MASTER_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "CORS_ORIGINS": "http://localhost:3000",
}


def main() -> None:
    # Set before importing the app: `metis.entrypoints.api` builds it at import time.
    os.environ.update(PLACEHOLDER_SETTINGS)
    from metis.entrypoints.api import create_app

    schema = create_app().openapi()
    sys.stdout.write(json.dumps(schema, indent=2, sort_keys=True))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
