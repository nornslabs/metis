"""BYO provider keys and workspace settings (SHIP-217).

Seam: HTTP requests against the real FastAPI app as the non-superuser
``metis_app`` role (see ``conftest.py``). LLM calls go to an
``httpx.MockTransport``; Exa calls go to an in-process fake Exa MCP server
(``fake_exa_mcp.py``). Nothing leaves the process.
``get_key_for_use`` has no route, so it is checked through the service on a
session scoped like a request.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from api_helpers import APP_ROLE, add_member_directly, assert_problem, bearer, make_token, me
from fake_exa_mcp import ExaMode, FakeExaMcp
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from metis.adapters.mcp.exa import EXA_MCP_URL
from metis.core.config import get_settings
from metis.core.errors import ProviderNotConfiguredError
from metis.entrypoints.api import app
from metis.helpers import http as provider_http
from metis.helpers.http import ClientFactory, provider_http_factory
from metis.modules import identity
from metis.modules.identity import ProviderKind

LLM_KEY = "sk-test-0123456789abcdef"
EXA_KEY = "exa-test-0123456789abcd"
LLM_BASE_URL = "https://llm.example.com/v1"
LLM_MODEL = "gpt-4o-mini"
EXA_MCP_HOST = httpx.URL(EXA_MCP_URL).host

Handler = Callable[[httpx.Request], httpx.Response]
AsyncHandler = Callable[[httpx.Request], Awaitable[httpx.Response]]
TINY_TIMEOUT_SECONDS = 0.05
SLOW_PROVIDER_SECONDS = 1.0


async def _slow(_request: httpx.Request) -> httpx.Response:
    """A provider that answers long after the total timeout."""
    await asyncio.sleep(SLOW_PROVIDER_SECONDS)
    return httpx.Response(200, json={"data": []})


# -------------------------------------------------------------------- fixtures
class FakeProvider:
    """Answers adapter calls with ``handler`` and records every request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.handler: Handler = lambda _request: httpx.Response(200, json={"data": []})
        self.async_handler: AsyncHandler | None = None

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.async_handler is not None:
            return await self.async_handler(request)
        return self.handler(request)


class _RoutingTransport(httpx.AsyncBaseTransport):
    """Exa's MCP host goes to the fake Exa server; everything else to the fake LLM."""

    def __init__(self, exa: httpx.AsyncBaseTransport, llm: httpx.AsyncBaseTransport) -> None:
        self._exa = exa
        self._llm = llm

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        target = self._exa if request.url.host == EXA_MCP_HOST else self._llm
        return await target.handle_async_request(request)


@pytest_asyncio.fixture
async def exa() -> AsyncIterator[FakeExaMcp]:
    async with FakeExaMcp().running() as fake:
        yield fake


@pytest_asyncio.fixture
async def provider(client: httpx.AsyncClient, exa: FakeExaMcp) -> AsyncIterator[FakeProvider]:
    fake = FakeProvider()
    transport = _RoutingTransport(exa.transport(), httpx.MockTransport(fake))

    def fake_factory() -> ClientFactory:
        return lambda headers: httpx.AsyncClient(transport=transport, headers=dict(headers))

    app.dependency_overrides[provider_http_factory] = fake_factory
    yield fake
    app.dependency_overrides.pop(provider_http_factory, None)


@pytest.fixture
def production_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_JSON", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


# --------------------------------------------------------------------- helpers
async def put_llm(
    client: httpx.AsyncClient,
    token: str,
    *,
    value: str = LLM_KEY,
    base_url: str | None = LLM_BASE_URL,
    model: str | None = LLM_MODEL,
    workspace: str | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {"value": value}
    if base_url is not None:
        body["base_url"] = base_url
    if model is not None:
        body["model"] = model
    return await client.put("/v1/settings/keys/llm", json=body, headers=bearer(token, workspace))


async def put_exa(
    client: httpx.AsyncClient, token: str, value: str = EXA_KEY, **extra: str
) -> httpx.Response:
    body = {"value": value, **extra}
    return await client.put("/v1/settings/keys/exa", json=body, headers=bearer(token))


async def get_settings_body(
    client: httpx.AsyncClient, token: str, workspace: str | None = None
) -> Any:
    response = await client.get("/v1/settings", headers=bearer(token, workspace))
    assert response.status_code == 200, response.text
    return response.json()


async def personal_workspace_id(client: httpx.AsyncClient, token: str) -> str:
    return str((await me(client, token))["current_workspace"]["workspace"]["id"])


async def key_for_use(
    engine: AsyncEngine, workspace_id: str, kind: ProviderKind = ProviderKind.LLM
) -> identity.ProviderCredentials:
    """Call ``get_key_for_use`` as the app role, scoped to ``workspace_id`` like a request."""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        await session.execute(
            text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": workspace_id}
        )
        return await identity.get_key_for_use(session, UUID(workspace_id), kind)


def assert_no_plaintext(response: httpx.Response, *secrets: str) -> None:
    for secret in secrets:
        assert secret not in response.text


# ----------------------------------------------------------------- GET settings
async def test_new_workspace_has_no_keys_and_default_settings(client: httpx.AsyncClient) -> None:
    body = await get_settings_body(client, make_token())

    assert body["keys"] == {"llm": None, "exa": None}
    assert body["settings"] == {"run_budget_usd": 2.0, "max_steps": 50, "version": 0}


async def test_settings_need_a_token(client: httpx.AsyncClient) -> None:
    assert_problem(await client.get("/v1/settings"), 401, "auth.unauthorized")


# ----------------------------------------------------------------- PUT key
async def test_saved_llm_key_is_masked_and_never_returned(client: httpx.AsyncClient) -> None:
    token = make_token()

    saved = await put_llm(client, token)
    listed = await client.get("/v1/settings", headers=bearer(token))

    assert saved.status_code == 200, saved.text
    key = saved.json()
    assert key["kind"] == "llm"
    assert key["masked"] == "sk-…cdef"
    assert key["base_url"] == LLM_BASE_URL
    assert key["model"] == LLM_MODEL
    assert key["version"] == 1
    assert key["last_tested_at"] is None
    assert key["last_test_ok"] is None
    assert listed.json()["keys"]["llm"] == key
    assert_no_plaintext(saved, LLM_KEY)
    assert_no_plaintext(listed, LLM_KEY)


async def test_stored_key_is_encrypted_and_opens_only_through_get_key_for_use(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    token = make_token()
    await put_llm(client, token)
    workspace_id = await personal_workspace_id(client, token)

    async with engine.connect() as conn:
        sealed = await conn.scalar(text("SELECT sealed::text FROM identity.provider_keys"))
    creds = await key_for_use(engine, workspace_id)

    assert sealed is not None
    assert LLM_KEY not in sealed
    assert creds.api_key == LLM_KEY
    assert creds.base_url == LLM_BASE_URL
    assert creds.model == LLM_MODEL


async def test_saving_again_replaces_the_key_and_clears_the_test_result(
    client: httpx.AsyncClient, provider: FakeProvider, engine: AsyncEngine
) -> None:
    token = make_token()
    await put_llm(client, token)
    await client.post("/v1/settings/keys/llm/test", headers=bearer(token))

    replaced = await put_llm(client, token, value="sk-new-key-9876543210zz")
    creds = await key_for_use(engine, await personal_workspace_id(client, token))

    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["version"] == 2
    assert replaced.json()["masked"] == "sk-…10zz"
    assert replaced.json()["last_tested_at"] is None
    assert replaced.json()["last_test_ok"] is None
    assert creds.api_key == "sk-new-key-9876543210zz"


async def test_exa_key_needs_no_base_url_or_model(client: httpx.AsyncClient) -> None:
    response = await put_exa(client, make_token())

    assert response.status_code == 200, response.text
    assert response.json()["base_url"] is None
    assert response.json()["model"] is None
    assert_no_plaintext(response, EXA_KEY)


async def test_base_url_trailing_slash_is_normalised(client: httpx.AsyncClient) -> None:
    response = await put_llm(client, make_token(), base_url=LLM_BASE_URL + "/")

    assert response.json()["base_url"] == LLM_BASE_URL


@pytest.mark.parametrize(
    ("body", "kind"),
    [
        ({"value": LLM_KEY, "base_url": "http://llm.example.com/v1", "model": "m"}, "llm"),
        ({"value": LLM_KEY, "base_url": "ftp://llm.example.com", "model": "m"}, "llm"),
        ({"value": LLM_KEY, "base_url": "not a url", "model": "m"}, "llm"),
        ({"value": LLM_KEY, "model": "m"}, "llm"),
        ({"value": LLM_KEY, "base_url": LLM_BASE_URL}, "llm"),
        ({"value": LLM_KEY, "base_url": LLM_BASE_URL, "model": "  "}, "llm"),
        ({"value": "   ", "base_url": LLM_BASE_URL, "model": "m"}, "llm"),
        ({"value": "x" * 513, "base_url": LLM_BASE_URL, "model": "m"}, "llm"),
        ({"value": EXA_KEY, "base_url": LLM_BASE_URL}, "exa"),
        ({"value": EXA_KEY, "model": "m"}, "exa"),
        ({"base_url": LLM_BASE_URL, "model": "m"}, "llm"),
    ],
)
async def test_invalid_key_input_is_422_without_echoing_the_key(
    client: httpx.AsyncClient, body: dict[str, str], kind: str
) -> None:
    response = await client.put(
        f"/v1/settings/keys/{kind}", json=body, headers=bearer(make_token())
    )

    assert_problem(response, 422, "common.validation_failed")
    assert_no_plaintext(response, LLM_KEY, EXA_KEY)


async def test_unknown_kind_is_422(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/v1/settings/keys/anthropic", json={"value": LLM_KEY}, headers=bearer(make_token())
    )

    assert_problem(response, 422, "common.validation_failed")


async def test_local_http_base_url_is_allowed_in_development(client: httpx.AsyncClient) -> None:
    response = await put_llm(client, make_token(), base_url="http://localhost:11434/v1")

    assert response.status_code == 200, response.text
    assert response.json()["base_url"] == "http://localhost:11434/v1"


@pytest.mark.usefixtures("production_env")
async def test_local_http_base_url_is_refused_outside_development(
    client: httpx.AsyncClient,
) -> None:
    response = await put_llm(client, make_token(), base_url="http://localhost:11434/v1")

    assert_problem(response, 422, "common.validation_failed")


# ----------------------------------------------------------------- DELETE key
async def test_deleted_key_is_gone(client: httpx.AsyncClient) -> None:
    token = make_token()
    await put_llm(client, token)

    deleted = await client.delete("/v1/settings/keys/llm", headers=bearer(token))

    assert deleted.status_code == 204, deleted.text
    assert (await get_settings_body(client, token))["keys"]["llm"] is None


async def test_deleting_a_missing_key_is_404(client: httpx.AsyncClient) -> None:
    response = await client.delete("/v1/settings/keys/exa", headers=bearer(make_token()))

    assert_problem(response, 404, "provider.key_not_found")


# ----------------------------------------------------------------- test key
async def test_llm_key_test_lists_models_with_the_key(
    client: httpx.AsyncClient, provider: FakeProvider
) -> None:
    token = make_token()
    await put_llm(client, token)
    provider.handler = lambda _r: httpx.Response(200, json={"data": [{"id": LLM_MODEL}]})

    response = await client.post("/v1/settings/keys/llm/test", headers=bearer(token))

    assert response.status_code == 200, response.text
    assert response.json()["last_test_ok"] is True
    assert response.json()["last_tested_at"] is not None
    assert_no_plaintext(response, LLM_KEY)
    [sent] = provider.requests
    assert sent.method == "GET"
    assert str(sent.url) == f"{LLM_BASE_URL}/models"
    assert sent.headers["authorization"] == f"Bearer {LLM_KEY}"


@pytest.mark.usefixtures("provider")
async def test_exa_key_test_calls_web_search_once_over_mcp_with_the_key(
    client: httpx.AsyncClient, exa: FakeExaMcp
) -> None:
    token = make_token()
    await put_exa(client, token)

    response = await client.post("/v1/settings/keys/exa/test", headers=bearer(token))

    assert response.status_code == 200, response.text
    assert response.json()["last_test_ok"] is True
    assert_no_plaintext(response, EXA_KEY)
    [call] = exa.tool_calls
    assert call["numResults"] == 1
    assert exa.api_keys
    assert set(exa.api_keys) == {EXA_KEY}


@pytest.mark.usefixtures("provider")
@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        (ExaMode.BAD_KEY, "unauthorized"),
        (ExaMode.HTTP_401, "unauthorized"),
        (ExaMode.TOOL_ERROR, "bad_response"),
        (ExaMode.UNREACHABLE, "unreachable"),
    ],
)
async def test_failed_exa_key_test_is_502_and_is_recorded(
    client: httpx.AsyncClient, exa: FakeExaMcp, mode: ExaMode, reason: str
) -> None:
    token = make_token()
    await put_exa(client, token)
    exa.mode = mode

    response = await client.post("/v1/settings/keys/exa/test", headers=bearer(token))
    stored = (await get_settings_body(client, token))["keys"]["exa"]

    assert_problem(response, 502, "provider.upstream_error")
    assert response.json()["meta"] == {"provider": "exa", "reason": reason}
    assert_no_plaintext(response, EXA_KEY)
    assert stored["last_test_ok"] is False


@pytest.mark.usefixtures("provider")
async def test_exa_key_test_is_capped_at_the_total_timeout(
    client: httpx.AsyncClient, exa: FakeExaMcp, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = make_token()
    await put_exa(client, token)
    monkeypatch.setattr(provider_http, "PROVIDER_TIMEOUT_SECONDS", TINY_TIMEOUT_SECONDS)
    exa.mode = ExaMode.SLOW

    response = await client.post("/v1/settings/keys/exa/test", headers=bearer(token))

    assert_problem(response, 502, "provider.upstream_error")
    assert response.json()["meta"] == {"provider": "exa", "reason": "timeout"}


def _raise(exc: Exception) -> Handler:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


@pytest.mark.parametrize(
    ("handler", "reason"),
    [
        (lambda _r: httpx.Response(401, json={"error": "bad key " + LLM_KEY}), "unauthorized"),
        (lambda _r: httpx.Response(403), "unauthorized"),
        (lambda _r: httpx.Response(500, text="boom"), "bad_response"),
        (lambda _r: httpx.Response(200, text="not json"), "bad_response"),
        (lambda _r: httpx.Response(200, json={"unexpected": True}), "bad_response"),
        (_raise(httpx.ConnectError("no route")), "unreachable"),
        (_raise(httpx.ReadTimeout("slow")), "timeout"),
    ],
)
async def test_failed_key_test_is_502_and_is_recorded(
    client: httpx.AsyncClient, provider: FakeProvider, handler: Handler, reason: str
) -> None:
    token = make_token()
    await put_llm(client, token)
    provider.handler = handler

    response = await client.post("/v1/settings/keys/llm/test", headers=bearer(token))
    stored = (await get_settings_body(client, token))["keys"]["llm"]

    assert_problem(response, 502, "provider.upstream_error")
    assert response.json()["meta"] == {"provider": "llm", "reason": reason}
    assert_no_plaintext(response, LLM_KEY)
    assert stored["last_test_ok"] is False
    assert stored["last_tested_at"] is not None


async def test_key_test_is_capped_at_the_total_timeout(
    client: httpx.AsyncClient, provider: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = make_token()
    await put_llm(client, token)
    monkeypatch.setattr(provider_http, "PROVIDER_TIMEOUT_SECONDS", TINY_TIMEOUT_SECONDS)
    provider.async_handler = _slow

    response = await client.post("/v1/settings/keys/llm/test", headers=bearer(token))

    assert_problem(response, 502, "provider.upstream_error")
    assert response.json()["meta"] == {"provider": "llm", "reason": "timeout"}


@pytest.mark.usefixtures("provider")
async def test_testing_a_missing_key_is_not_configured(
    client: httpx.AsyncClient, exa: FakeExaMcp
) -> None:
    response = await client.post("/v1/settings/keys/exa/test", headers=bearer(make_token()))

    assert_problem(response, 402, "provider.not_configured")
    assert exa.api_keys == []


# ----------------------------------------------------------------- PATCH settings
async def test_first_patch_creates_settings_from_version_zero(client: httpx.AsyncClient) -> None:
    token = make_token()

    response = await client.patch(
        "/v1/settings", json={"version": 0, "max_steps": 80}, headers=bearer(token)
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"run_budget_usd": 2.0, "max_steps": 80, "version": 1}
    assert (await get_settings_body(client, token))["settings"] == response.json()


async def test_patch_with_current_version_updates_and_bumps_version(
    client: httpx.AsyncClient,
) -> None:
    token = make_token()
    await client.patch("/v1/settings", json={"version": 0, "max_steps": 80}, headers=bearer(token))

    response = await client.patch(
        "/v1/settings", json={"version": 1, "run_budget_usd": 7.5}, headers=bearer(token)
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"run_budget_usd": 7.5, "max_steps": 80, "version": 2}


@pytest.mark.parametrize("stale", [0, 1, 5])
async def test_patch_with_stale_version_is_409(client: httpx.AsyncClient, stale: int) -> None:
    token = make_token()
    await client.patch("/v1/settings", json={"version": 0, "max_steps": 80}, headers=bearer(token))
    await client.patch("/v1/settings", json={"version": 1, "max_steps": 90}, headers=bearer(token))

    response = await client.patch(
        "/v1/settings", json={"version": stale, "max_steps": 10}, headers=bearer(token)
    )

    assert_problem(response, 409, "common.conflict")
    assert (await get_settings_body(client, token))["settings"]["max_steps"] == 90


@pytest.mark.parametrize(
    "body",
    [
        {"version": 0, "run_budget_usd": 0},
        {"version": 0, "run_budget_usd": -1},
        {"version": 0, "run_budget_usd": 100.01},
        {"version": 0, "run_budget_usd": 1.005},
        {"version": 0, "max_steps": 0},
        {"version": 0, "max_steps": 201},
        {"version": 0},
        {"max_steps": 10},
        {"version": -1, "max_steps": 10},
    ],
)
async def test_invalid_settings_patch_is_422(
    client: httpx.AsyncClient, body: dict[str, Any]
) -> None:
    response = await client.patch("/v1/settings", json=body, headers=bearer(make_token()))

    assert_problem(response, 422, "common.validation_failed")


async def test_settings_bounds_are_inclusive(client: httpx.AsyncClient) -> None:
    response = await client.patch(
        "/v1/settings",
        json={"version": 0, "run_budget_usd": 100, "max_steps": 200},
        headers=bearer(make_token()),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"run_budget_usd": 100.0, "max_steps": 200, "version": 1}


# ----------------------------------------------------------------- owners only
async def team_with_member(client: httpx.AsyncClient, engine: AsyncEngine) -> tuple[str, str]:
    """Ada owns a team workspace with a saved LLM key; Bob is a plain member."""
    ada, bob = make_token(), make_token("auth|bob", "bob@example.com", "Bob")
    created = await client.post("/v1/workspaces", json={"name": "Team"}, headers=bearer(ada))
    team_id = created.json()["workspace"]["id"]
    bob_id = (await me(client, bob))["user"]["id"]
    await add_member_directly(engine, team_id, bob_id)
    await put_llm(client, ada, workspace=team_id)
    return team_id, bob


async def test_members_cannot_change_keys_or_settings(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    team_id, bob = await team_with_member(client, engine)
    headers = bearer(bob, team_id)

    put = await client.put("/v1/settings/keys/exa", json={"value": EXA_KEY}, headers=headers)
    delete = await client.delete("/v1/settings/keys/llm", headers=headers)
    patch = await client.patch(
        "/v1/settings", json={"version": 0, "max_steps": 10}, headers=headers
    )

    assert_problem(put, 403, "auth.forbidden")
    assert_problem(delete, 403, "auth.forbidden")
    assert_problem(patch, 403, "auth.forbidden")


async def test_members_can_read_and_test_keys(
    client: httpx.AsyncClient, engine: AsyncEngine, provider: FakeProvider
) -> None:
    team_id, bob = await team_with_member(client, engine)

    body = await get_settings_body(client, bob, team_id)
    tested = await client.post("/v1/settings/keys/llm/test", headers=bearer(bob, team_id))

    assert body["keys"]["llm"]["masked"] == "sk-…cdef"
    assert tested.status_code == 200, tested.text


# ----------------------------------------------------------------- isolation
async def test_keys_and_settings_are_scoped_to_their_workspace(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada, bob = make_token(), make_token("auth|bob", "bob@example.com", "Bob")
    await put_llm(client, ada)
    await client.patch("/v1/settings", json={"version": 0, "max_steps": 80}, headers=bearer(ada))
    bob_workspace = await personal_workspace_id(client, bob)

    bobs_view = await get_settings_body(client, bob)
    with pytest.raises(ProviderNotConfiguredError):
        await key_for_use(engine, bob_workspace)

    assert bobs_view["keys"] == {"llm": None, "exa": None}
    assert bobs_view["settings"]["max_steps"] == 50
