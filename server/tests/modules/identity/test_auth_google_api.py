"""Google sign-in: login, callback, sign-up / linking, logout and logout-all.

Seam: HTTP requests against the real FastAPI app (``ASGITransport``). Postgres
is migrated to head (request session as ``metis_app``) and Redis is real
(``TEST_REDIS_URL``). Google is faked by ``FakeGoogle`` behind
``httpx.MockTransport``: the provider dependency is overridden with a
``GoogleProvider`` whose HTTP client goes to the fake. Tests drive the real
flow: ``/login`` gives the ``state`` and ``nonce``, then ``/callback`` finishes.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from api_helpers import assert_problem, make_token, me
from fake_google import AUTHORIZATION_URL, EMAIL, SUBJECT, FakeGoogle, new_rsa_key
from redis.asyncio import Redis
from session_probe import PROBE
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from structlog.testing import capture_logs

from metis.core.config import get_settings
from metis.core.errors import OAuthFailedError
from metis.core.redis import get_redis
from metis.entrypoints.api import app
from metis.modules.identity import auth_service
from metis.modules.identity.oauth_flow import OAUTH_KEY_PREFIX, OAUTH_STATE_TTL_SECONDS
from metis.modules.identity.providers import get_google_provider
from metis.modules.identity.providers.google import GoogleProvider

SETTINGS = get_settings()
WEB = SETTINGS.web_base_url.rstrip("/")
COOKIE = SETTINGS.session_cookie_name
WEB_CLIENT = {"X-Metis-Client": "web"}
LOGIN = "/v1/auth/google/login"
CALLBACK = "/v1/auth/google/callback"


# -------------------------------------------------------------------- fixtures
@pytest.fixture
def google() -> FakeGoogle:
    return FakeGoogle(client_id=SETTINGS.google_client_id or "")


def _provider(google: FakeGoogle) -> GoogleProvider:
    secret = SETTINGS.google_client_secret
    assert secret is not None and SETTINGS.google_redirect_uri is not None
    return GoogleProvider(
        client_id=google.client_id,
        client_secret=secret.get_secret_value(),
        redirect_uri=SETTINGS.google_redirect_uri,
        client_factory=lambda headers: httpx.AsyncClient(
            transport=google.transport(), headers=dict(headers)
        ),
    )


@pytest_asyncio.fixture
async def api(http: httpx.AsyncClient, google: FakeGoogle) -> AsyncIterator[httpx.AsyncClient]:
    provider = _provider(google)
    app.dependency_overrides[get_google_provider] = lambda: provider
    yield http
    http.cookies.clear()


# --------------------------------------------------------------------- helpers
def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


async def _login(api: httpx.AsyncClient, google: FakeGoogle, redirect_to: str | None = None) -> str:
    """Start a login; hand the fake its nonce. Returns the ``state``."""
    params = {} if redirect_to is None else {"redirect_to": redirect_to}
    response = await api.get(LOGIN, params=params)
    assert response.status_code == 302, response.text
    query = _query(response.headers["location"])
    google.nonce = query["nonce"]
    return query["state"]


async def _callback(api: httpx.AsyncClient, state: str, code: str = "auth-code") -> httpx.Response:
    response = await api.get(CALLBACK, params={"code": code, "state": state})
    api.cookies.clear()  # tests pass cookies explicitly
    return response


async def _sign_in(
    api: httpx.AsyncClient, google: FakeGoogle, redirect_to: str | None = None
) -> httpx.Response:
    return await _callback(api, await _login(api, google, redirect_to))


def _session_token(response: httpx.Response) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        name, _, rest = header.partition("=")
        if name == COOKIE:
            value = rest.split(";", 1)[0]
            return value or None
    return None


def _sign_in_error(response: httpx.Response) -> str | None:
    assert response.status_code == 302, response.text
    location = response.headers["location"]
    if not location.startswith(f"{WEB}/sign-in"):
        return None
    return _query(location).get("error")


def _cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"{COOKIE}={token}"}


async def _whoami(api: httpx.AsyncClient, token: str) -> httpx.Response:
    return await api.get(PROBE, headers=_cookie(token))


async def _rows(engine: AsyncEngine, sql: str, **params: Any) -> list[Any]:
    async with engine.begin() as conn:
        return list((await conn.execute(text(sql), params)).all())


async def _count(engine: AsyncEngine, table: str) -> int:
    return (await _rows(engine, f"SELECT count(*) FROM {table}"))[0][0]


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ------------------------------------------------------------------ providers
async def test_providers_lists_google(api: httpx.AsyncClient) -> None:
    response = await api.get("/v1/auth/providers")

    assert response.status_code == 200
    assert response.json() == ["google"]


async def test_providers_is_empty_when_google_is_not_configured(http: httpx.AsyncClient) -> None:
    app.dependency_overrides[get_google_provider] = lambda: None

    response = await http.get("/v1/auth/providers")

    assert response.json() == []


# ---------------------------------------------------------------------- login
async def test_login_redirects_to_google_with_pkce_state_and_nonce(
    api: httpx.AsyncClient, redis: Redis
) -> None:
    response = await api.get(LOGIN)

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(AUTHORIZATION_URL + "?")
    query = _query(location)
    assert query["response_type"] == "code"
    assert query["client_id"] == SETTINGS.google_client_id
    assert query["redirect_uri"] == SETTINGS.google_redirect_uri
    assert query["scope"] == "openid email profile"
    assert query["code_challenge_method"] == "S256"
    assert len(query["code_challenge"]) == 43
    assert query["state"] and query["nonce"] and query["state"] != query["nonce"]
    ttl = await redis.ttl(OAUTH_KEY_PREFIX + query["state"])
    assert 0 < ttl <= OAUTH_STATE_TTL_SECONDS


async def test_login_without_google_config_redirects_to_sign_in_error(
    http: httpx.AsyncClient,
) -> None:
    app.dependency_overrides[get_google_provider] = lambda: None

    response = await http.get(LOGIN)

    assert _sign_in_error(response) == "auth.oauth_failed"


async def test_login_when_redis_is_down_redirects_to_sign_in_error(
    api: httpx.AsyncClient,
) -> None:
    down: Redis = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    app.dependency_overrides[get_redis] = lambda: down

    response = await api.get(LOGIN)

    assert _sign_in_error(response) == "auth.oauth_failed"
    await down.aclose()


# ------------------------------------------------------------------- sign-up
async def test_first_sign_in_creates_user_workspace_identity_and_session(
    api: httpx.AsyncClient, google: FakeGoogle, engine: AsyncEngine
) -> None:
    response = await _sign_in(api, google, redirect_to="/ideas/123?tab=score")

    assert response.status_code == 302
    assert response.headers["location"] == f"{WEB}/ideas/123?tab=score"
    token = _session_token(response)
    assert token is not None
    whoami = await _whoami(api, token)
    assert whoami.status_code == 200
    users = await _rows(engine, "SELECT id, email, name, image, auth_sub FROM identity.users")
    assert len(users) == 1
    user_id, email, name, image, auth_sub = users[0]
    assert whoami.json()["user_id"] == str(user_id)
    assert (email, name, auth_sub) == (EMAIL, "Ada Lovelace", SUBJECT)
    assert image == "https://lh3.googleusercontent.com/a/ada"
    workspaces = await _rows(engine, "SELECT created_by FROM identity.workspaces WHERE is_personal")
    assert workspaces == [(user_id,)]
    identities = await _rows(
        engine,
        "SELECT user_id, provider, subject, email, email_verified, last_login_at "
        "FROM identity.auth_identities",
    )
    assert len(identities) == 1
    assert identities[0][:5] == (user_id, "google", SUBJECT, EMAIL, True)
    assert identities[0][5] is not None


async def test_second_sign_in_reuses_the_user_and_advances_last_login(
    api: httpx.AsyncClient, google: FakeGoogle, engine: AsyncEngine
) -> None:
    first = _session_token(await _sign_in(api, google))
    before = (await _rows(engine, "SELECT last_login_at FROM identity.auth_identities"))[0][0]

    second = _session_token(await _sign_in(api, google))

    assert first and second and first != second
    assert (await _whoami(api, first)).json()["user_id"] == (await _whoami(api, second)).json()[
        "user_id"
    ]
    assert await _count(engine, "identity.users") == 1
    assert await _count(engine, "identity.workspaces") == 1
    assert await _count(engine, "identity.auth_identities") == 1
    after = (await _rows(engine, "SELECT last_login_at FROM identity.auth_identities"))[0][0]
    assert after > before


async def test_verified_email_match_links_the_existing_user(
    api: httpx.AsyncClient, google: FakeGoogle, engine: AsyncEngine
) -> None:
    existing = await me(api, make_token(sub="auth|legacy-ada", email=EMAIL))
    existing_id = existing["user"]["id"]

    token = _session_token(await _sign_in(api, google))

    assert token is not None
    assert (await _whoami(api, token)).json()["user_id"] == existing_id
    assert await _count(engine, "identity.users") == 1
    assert await _count(engine, "identity.workspaces") == 1
    identities = await _rows(engine, "SELECT user_id, subject FROM identity.auth_identities")
    assert identities == [(UUID(existing_id), SUBJECT)]


async def test_user_with_the_google_subject_as_auth_sub_is_found(
    api: httpx.AsyncClient, google: FakeGoogle, engine: AsyncEngine
) -> None:
    existing = await me(api, make_token(sub=SUBJECT, email="old-ada@example.com"))

    token = _session_token(await _sign_in(api, google))

    assert token is not None
    assert (await _whoami(api, token)).json()["user_id"] == existing["user"]["id"]
    assert await _count(engine, "identity.users") == 1


async def test_backfilled_identity_is_found_by_subject(
    api: httpx.AsyncClient, google: FakeGoogle, engine: AsyncEngine
) -> None:
    existing = await me(api, make_token(sub="auth|other", email="other@example.com"))
    await _rows(
        engine,
        "INSERT INTO identity.auth_identities (id, user_id, provider, subject, email, "
        "email_verified) VALUES (gen_random_uuid(), :user_id, 'google', :sub, :email, true) "
        "RETURNING id",
        user_id=existing["user"]["id"],
        sub=SUBJECT,
        email="other@example.com",
    )

    token = _session_token(await _sign_in(api, google))

    assert token is not None
    assert (await _whoami(api, token)).json()["user_id"] == existing["user"]["id"]
    assert await _count(engine, "identity.users") == 1


async def test_unverified_email_is_refused(
    api: httpx.AsyncClient, google: FakeGoogle, engine: AsyncEngine
) -> None:
    google.claims = {"email_verified": False}

    response = await _sign_in(api, google)

    assert _sign_in_error(response) == "auth.email_unverified"
    assert _session_token(response) is None
    assert await _count(engine, "identity.users") == 0


async def test_failure_after_the_user_is_created_leaves_nothing_behind(
    api: httpx.AsyncClient,
    google: FakeGoogle,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_create_session(*_: object, **__: object) -> None:
        raise OAuthFailedError("session store down")

    monkeypatch.setattr(auth_service, "create_session", failing_create_session)

    response = await _sign_in(api, google)

    assert _sign_in_error(response) == "auth.oauth_failed"
    assert _session_token(response) is None
    assert await _count(engine, "identity.users") == 0
    assert await _count(engine, "identity.workspaces") == 0
    assert await _count(engine, "identity.auth_identities") == 0


async def test_unverified_email_is_refused_even_for_a_known_identity(
    api: httpx.AsyncClient, google: FakeGoogle
) -> None:
    await _sign_in(api, google)
    google.claims = {"email_verified": False}

    response = await _sign_in(api, google)

    assert _sign_in_error(response) == "auth.email_unverified"


# ---------------------------------------------------------------------- state
async def test_reused_state_is_rejected(api: httpx.AsyncClient, google: FakeGoogle) -> None:
    state = await _login(api, google)
    assert _session_token(await _callback(api, state)) is not None

    replay = await _callback(api, state)

    assert _sign_in_error(replay) == "auth.oauth_state_invalid"
    assert _session_token(replay) is None


async def test_unknown_state_is_rejected(api: httpx.AsyncClient, google: FakeGoogle) -> None:
    await _login(api, google)

    response = await _callback(api, "never-issued")

    assert _sign_in_error(response) == "auth.oauth_state_invalid"


async def test_expired_state_is_rejected(
    api: httpx.AsyncClient, google: FakeGoogle, redis: Redis
) -> None:
    state = await _login(api, google)
    await redis.delete(OAUTH_KEY_PREFIX + state)  # what the 10 min TTL does

    response = await _callback(api, state)

    assert _sign_in_error(response) == "auth.oauth_state_invalid"


async def test_callback_without_state_or_code_is_rejected(api: httpx.AsyncClient) -> None:
    response = await api.get(CALLBACK)

    assert _sign_in_error(response) == "auth.oauth_state_invalid"


async def test_callback_without_code_fails(api: httpx.AsyncClient, google: FakeGoogle) -> None:
    state = await _login(api, google)

    response = await api.get(CALLBACK, params={"state": state})

    assert _sign_in_error(response) == "auth.oauth_failed"


async def test_google_error_on_callback_fails(api: httpx.AsyncClient, google: FakeGoogle) -> None:
    state = await _login(api, google)

    response = await api.get(CALLBACK, params={"state": state, "error": "access_denied"})

    assert _sign_in_error(response) == "auth.oauth_failed"
    assert google.token_requests == []


# -------------------------------------------------------------------- id_token
@pytest.mark.parametrize(
    "claims",
    [
        pytest.param({"aud": "someone-else.apps.googleusercontent.com"}, id="wrong-aud"),
        pytest.param({"iss": "https://evil.example"}, id="wrong-iss"),
        pytest.param({"nonce": "not-the-nonce"}, id="wrong-nonce"),
        pytest.param({"exp": 1_000_000_000}, id="expired"),
        pytest.param({"sub": None}, id="no-sub"),
        pytest.param({"email": None}, id="no-email"),
    ],
)
async def test_tampered_id_token_is_rejected(
    api: httpx.AsyncClient, google: FakeGoogle, engine: AsyncEngine, claims: dict[str, Any]
) -> None:
    state = await _login(api, google)
    google.claims = claims

    response = await _callback(api, state)

    assert _sign_in_error(response) == "auth.oauth_failed"
    assert _session_token(response) is None
    assert await _count(engine, "identity.users") == 0


async def test_id_token_signed_by_another_key_is_rejected(
    api: httpx.AsyncClient, google: FakeGoogle, engine: AsyncEngine
) -> None:
    google.signing_key = new_rsa_key()

    response = await _sign_in(api, google)

    assert _sign_in_error(response) == "auth.oauth_failed"
    assert await _count(engine, "identity.users") == 0


async def test_rotated_google_key_is_fetched_again(
    api: httpx.AsyncClient, google: FakeGoogle
) -> None:
    assert _session_token(await _sign_in(api, google)) is not None
    google.rotate_key("test-key-2")

    response = await _sign_in(api, google)

    assert _session_token(response) is not None
    assert google.jwks_fetches == 2


@pytest.mark.parametrize(
    ("status", "body", "network_down"),
    [
        pytest.param(400, None, False, id="400"),
        pytest.param(500, None, False, id="500"),
        pytest.param(200, "not json", False, id="malformed"),
        pytest.param(200, '{"access_token": "x"}', False, id="no-id-token"),
        pytest.param(200, None, True, id="network"),
    ],
)
async def test_token_endpoint_failure_is_oauth_failed(
    api: httpx.AsyncClient,
    google: FakeGoogle,
    status: int,
    body: str | None,
    network_down: bool,
) -> None:
    state = await _login(api, google)
    google.token_status, google.token_body, google.network_down = status, body, network_down

    response = await _callback(api, state)

    assert _sign_in_error(response) == "auth.oauth_failed"


async def test_token_exchange_sends_the_matching_pkce_verifier(
    api: httpx.AsyncClient, google: FakeGoogle
) -> None:
    login = await api.get(LOGIN)
    query = _query(login.headers["location"])
    google.nonce = query["nonce"]

    await _callback(api, query["state"], code="the-code")

    (sent,) = google.token_requests
    assert sent["grant_type"] == "authorization_code"
    assert sent["code"] == "the-code"
    assert sent["redirect_uri"] == SETTINGS.google_redirect_uri
    assert sent["client_id"] == SETTINGS.google_client_id
    assert sent["client_secret"] == "test-google-client-secret"
    assert _challenge(sent["code_verifier"]) == query["code_challenge"]


# ------------------------------------------------------------------ redirect_to
@pytest.mark.parametrize(
    "redirect_to",
    [
        "https://evil.example",
        "//evil.example/path",
        "/\\evil.example",
        "javascript:alert(1)",
        "ideas/1",
        "",
    ],
)
async def test_unsafe_redirect_to_falls_back_to_root(
    api: httpx.AsyncClient, google: FakeGoogle, redirect_to: str
) -> None:
    response = await _sign_in(api, google, redirect_to=redirect_to)

    assert response.headers["location"] == f"{WEB}/"


async def test_missing_redirect_to_goes_to_root(api: httpx.AsyncClient, google: FakeGoogle) -> None:
    response = await _sign_in(api, google)

    assert response.headers["location"] == f"{WEB}/"


# --------------------------------------------------------------------- logout
async def test_logout_revokes_the_session_and_clears_the_cookie(
    api: httpx.AsyncClient, google: FakeGoogle
) -> None:
    token = _session_token(await _sign_in(api, google))
    assert token is not None

    response = await api.post("/v1/auth/logout", headers={**_cookie(token), **WEB_CLIENT})

    assert response.status_code == 204
    cleared = response.headers["set-cookie"].lower()
    assert cleared.startswith(f"{COOKIE}=") and "max-age=0" in cleared
    assert_problem(await _whoami(api, token), 401, "auth.session_expired")


async def test_logout_without_a_session_is_204(api: httpx.AsyncClient) -> None:
    response = await api.post("/v1/auth/logout", headers=WEB_CLIENT)

    assert response.status_code == 204


async def test_logout_of_an_unknown_token_is_204(api: httpx.AsyncClient) -> None:
    response = await api.post("/v1/auth/logout", headers={**_cookie("garbage"), **WEB_CLIENT})

    assert response.status_code == 204


@pytest.mark.parametrize("path", ["/v1/auth/logout", "/v1/auth/logout-all"])
async def test_logout_routes_need_the_client_header(
    api: httpx.AsyncClient, google: FakeGoogle, path: str
) -> None:
    token = _session_token(await _sign_in(api, google))
    assert token is not None

    response = await api.post(path, headers=_cookie(token))

    assert_problem(response, 403, "auth.csrf_failed")
    assert (await _whoami(api, token)).status_code == 200


async def test_logout_all_without_a_session_is_401(api: httpx.AsyncClient) -> None:
    response = await api.post("/v1/auth/logout-all", headers=WEB_CLIENT)

    assert_problem(response, 401, "auth.not_signed_in")


async def test_logout_all_signs_out_every_session_of_the_user_only(
    api: httpx.AsyncClient, google: FakeGoogle
) -> None:
    laptop = _session_token(await _sign_in(api, google))
    phone = _session_token(await _sign_in(api, google))
    google.claims = {"sub": "google-sub-grace", "email": "grace@example.com"}
    other = _session_token(await _sign_in(api, google))
    assert laptop and phone and other
    assert (await _whoami(api, laptop)).status_code == 200  # cache it

    response = await api.post("/v1/auth/logout-all", headers={**_cookie(phone), **WEB_CLIENT})

    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert_problem(await _whoami(api, laptop), 401, "auth.session_expired")
    assert_problem(await _whoami(api, phone), 401, "auth.session_expired")
    assert (await _whoami(api, other)).status_code == 200


# -------------------------------------------------------------------- logging
async def test_secrets_never_reach_the_logs(api: httpx.AsyncClient, google: FakeGoogle) -> None:
    with capture_logs() as logs:
        state = await _login(api, google)
        response = await _callback(api, state, code="secret-auth-code")
        google.claims = {"aud": "wrong"}
        await _sign_in(api, google)

    token = _session_token(response)
    (sent, _) = google.token_requests
    rendered = repr(logs)
    for secret in (
        "secret-auth-code",
        sent["code_verifier"],
        state,
        google.nonce or "",
        "test-google-client-secret",
        token or "",
        *google.issued_id_tokens,
    ):
        assert secret and secret not in rendered
    events = [entry["event"] for entry in logs]
    assert "auth.sign_in" in events
    assert "auth.oauth_failed" in events
