"""API docs module: protected Swagger UI and OpenAPI schema.

All docs endpoints require a valid session cookie via ``current_user``.
The default FastAPI docs URLs (``/docs``, ``/redoc``, ``/openapi.json`` at
root) are disabled in ``entrypoints/api.py`` and replaced by these
authenticated routes under ``/v1/docs/*``.
"""

from metis.modules.docs.controller import router

__all__ = ["router"]
