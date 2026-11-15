"""Every protected route requires a session cookie.

Seam: HTTP requests against the real FastAPI app. The test walks the app's route
table (``fastapi.routing.iter_route_contexts`` also walks included routers and
routes hidden from the OpenAPI schema), so a new ``/v1`` route that forgets its
auth dependency fails here unless it is added to :data:`PUBLIC_ROUTES` on
purpose.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from api_helpers import assert_problem, auth, sign_in
from fastapi.routing import APIRoute, iter_route_contexts
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.entrypoints.api import app

API_PREFIX = "/v1/"
# Test-only probe routes mounted by other test files; not part of the product.
TEST_ROUTE_PREFIX = "/v1/_test/"
PUBLIC_ROUTES = frozenset(
    {
        ("GET", "/v1/health"),
        ("GET", "/v1/auth/providers"),
        ("GET", "/v1/auth/google/login"),
        ("GET", "/v1/auth/google/callback"),
        ("POST", "/v1/auth/logout"),
    }
)
PATH_PARAM = re.compile(r"\{(\w+)(?::\w+)?\}")
PATH_PARAM_VALUES = {"kind": "llm"}
DEFAULT_PATH_PARAM = "00000000-0000-0000-0000-000000000000"
ANY_ROUTE_THAT_NEEDS_A_SESSION = "/v1/me"
OLD_JWT_SECRET = "test-jwt-secret-for-hs256-at-least-32-bytes"


def _protected_routes() -> list[tuple[str, str]]:
    routes = {
        (method, context.path)
        for context in iter_route_contexts(app.routes)
        if isinstance(context.route, APIRoute)
        and context.path.startswith(API_PREFIX)
        and not context.path.startswith(TEST_ROUTE_PREFIX)
        for method in context.route.methods
        if method != "HEAD"
    }
    return sorted(routes - PUBLIC_ROUTES)


def _concrete(path: str) -> str:
    return PATH_PARAM.sub(lambda m: PATH_PARAM_VALUES.get(m.group(1), DEFAULT_PATH_PARAM), path)


def test_the_route_table_has_protected_routes() -> None:
    assert ("GET", "/v1/me") in _protected_routes()
    assert ("POST", "/v1/auth/logout-all") in _protected_routes()


@pytest.mark.parametrize(("method", "path"), _protected_routes())
async def test_protected_route_without_cookie_is_401_not_signed_in(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, _concrete(path), headers={"X-Metis-Client": "web"})

    assert_problem(response, 401, "auth.not_signed_in")
    assert "www-authenticate" not in response.headers


async def test_old_style_bearer_token_alone_is_401_not_signed_in(
    client: httpx.AsyncClient,
) -> None:
    # The HS256 API token the web app used to mint before SHIP-267.
    claims = {
        "sub": "google-ada",
        "email": "ada@example.com",
        "aud": "metis",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    token = jwt.encode(claims, OLD_JWT_SECRET, algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get(ANY_ROUTE_THAT_NEEDS_A_SESSION, headers=headers)

    assert_problem(response, 401, "auth.not_signed_in")
    assert "www-authenticate" not in response.headers


async def test_session_cookie_is_accepted(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    token = await sign_in(engine)

    response = await client.get(ANY_ROUTE_THAT_NEEDS_A_SESSION, headers=auth(token))

    assert response.status_code == 200, response.text
