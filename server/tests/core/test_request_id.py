"""Every ``application/problem+json`` error carries the request's real ``request_id``.

Seam: HTTP through ``TestClient``. Assertions cover only what a client or an
operator sees: the problem body, the ``X-Request-ID`` header and the log lines.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from structlog.testing import capture_logs

from metis.core.error_handlers import register_error_handlers
from metis.core.errors import ConflictError
from metis.core.middleware import RequestContextMiddleware

SUPPLIED_REQUEST_ID = "req-test-1234"


def _build_app() -> FastAPI:
    """Wire the app the same way ``metis.entrypoints.api`` does."""
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/conflict")
    def conflict() -> None:
        raise ConflictError(detail="already exists")

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("kaboom")

    @app.get("/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app(), raise_server_exceptions=False)


def _logged_request_ids(logs: list[dict[str, Any]]) -> set[str]:
    return {entry["request_id"] for entry in logs if entry.get("request_id")}


@pytest.mark.parametrize(
    "path",
    ["/conflict", "/boom", "/items/not-an-int", "/missing-route"],
    ids=["metis_error", "unhandled", "validation", "not_found"],
)
def test_error_body_echoes_supplied_request_id(client: TestClient, path: str) -> None:
    response = client.get(path, headers={"X-Request-ID": SUPPLIED_REQUEST_ID})

    assert response.status_code >= 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["request_id"] == SUPPLIED_REQUEST_ID


def test_metis_error_keeps_its_catalog_status(client: TestClient) -> None:
    response = client.get("/conflict")

    assert response.status_code == 409
    assert response.json()["detail"] == "already exists"


@pytest.mark.parametrize("path", ["/conflict", "/missing-route"])
def test_generated_request_id_matches_response_header(client: TestClient, path: str) -> None:
    response = client.get(path)

    body_request_id = response.json()["request_id"]
    assert body_request_id
    assert body_request_id == response.headers["X-Request-ID"]


@pytest.mark.parametrize("path", ["/conflict", "/boom"])
def test_error_body_request_id_matches_log_line(client: TestClient, path: str) -> None:
    with capture_logs() as logs:
        response = client.get(path)

    body_request_id = response.json()["request_id"]
    assert body_request_id
    assert _logged_request_ids(logs) == {body_request_id}


def test_real_api_app_returns_request_id_on_errors() -> None:
    from metis.entrypoints.api import app

    response = TestClient(app).get(
        "/v1/does-not-exist", headers={"X-Request-ID": SUPPLIED_REQUEST_ID}
    )

    assert response.status_code == 404
    assert response.json()["request_id"] == SUPPLIED_REQUEST_ID
