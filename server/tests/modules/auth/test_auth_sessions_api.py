"""Server-side sessions: cookie auth, expiry, revocation, CSRF and storage.

Seam: HTTP requests against the real FastAPI app (``ASGITransport``) through
test-only probe routes that depend on ``CurrentUserDep``. Postgres is migrated
to head and the request session runs as ``metis_app``; Redis is real
(``TEST_REDIS_URL``). Sessions are created with ``auth_service.sessions.create_session``
and expiry is driven by editing session rows, not by mocking the clock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import pytest_asyncio
from redis.asyncio import Redis
from session_probe import COOKIE_PROBE, PROBE
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from structlog.testing import capture_logs

from metis.core import security
from metis.core.config import get_settings
from metis.core.redis import get_redis
from metis.entrypoints.api import app
from metis.modules.auth import cache, repo
from metis.modules.auth import service as auth_service
from metis.modules.auth.dto import SessionRecord
from tests.helpers.auth import assert_problem, create_user
from tests.helpers.migrations import load_migration

if TYPE_CHECKING:
    from uuid import UUID

WEB_ORIGIN = get_settings().get_cors_origins()[0]
COOKIE = get_settings().session_cookie_name
WEB_CLIENT = {"X-Metis-Client": "web"}


# -------------------------------------------------------------------- fixtures


async def _user_id(engine: AsyncEngine, sub: str = "google-ada", email: str = "ada@x.io") -> UUID:
    return await create_user(engine, sub=sub, email=email)


async def _new_session(engine: AsyncEngine, user_id: UUID) -> str:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        created = await auth_service.sessions.create_session(
            session, user_id, "pytest/1.0", "127.0.0.1"
        )
        await session.commit()
    return created.token


async def _exec(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.begin() as conn:
        result = await conn.execute(text(sql), params)
        return result.all() if result.returns_rows else None


def _cookie(token: str | None) -> dict[str, str]:
    return {} if token is None else {"Cookie": f"{COOKIE}={token}"}


async def _get(http: httpx.AsyncClient, token: str | None) -> httpx.Response:
    return await http.get(PROBE, headers=_cookie(token))


async def _post(
    http: httpx.AsyncClient, token: str, headers: dict[str, str] | None = None
) -> httpx.Response:
    return await http.post(PROBE, headers={**_cookie(token), **(headers or {})})


@pytest_asyncio.fixture
async def ada(http: httpx.AsyncClient, engine: AsyncEngine) -> tuple[UUID, str]:
    user_id = await _user_id(engine)
    return user_id, await _new_session(engine, user_id)


# ------------------------------------------------------------------- resolving
async def test_valid_cookie_resolves_to_its_user(
    http: httpx.AsyncClient, ada: tuple[UUID, str]
) -> None:
    user_id, token = ada

    response = await _get(http, token)

    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == str(user_id)


async def test_missing_cookie_is_401_not_signed_in(http: httpx.AsyncClient) -> None:
    response = await _get(http, None)

    assert_problem(response, 401, "auth.not_signed_in")
    assert "www-authenticate" not in response.headers


@pytest.mark.parametrize("token", ["garbage", "x" * 43])
async def test_unknown_token_is_401_session_expired(http: httpx.AsyncClient, token: str) -> None:
    response = await _get(http, token)

    assert_problem(response, 401, "auth.session_expired")


async def test_session_past_absolute_expiry_is_rejected(
    http: httpx.AsyncClient, engine: AsyncEngine, ada: tuple[UUID, str]
) -> None:
    _, token = ada
    await _exec(
        engine,
        "UPDATE auth.sessions SET expires_at = now() - interval '1 second'",
    )

    assert_problem(await _get(http, token), 401, "auth.session_expired")


async def test_session_idle_for_seven_days_is_rejected(
    http: httpx.AsyncClient, engine: AsyncEngine, ada: tuple[UUID, str]
) -> None:
    _, token = ada
    await _exec(
        engine,
        "UPDATE auth.sessions SET last_seen_at = now() - interval '7 days 1 second'",
    )

    assert_problem(await _get(http, token), 401, "auth.session_expired")


async def test_use_after_touch_interval_advances_last_seen(
    http: httpx.AsyncClient, engine: AsyncEngine, ada: tuple[UUID, str]
) -> None:
    _, token = ada
    old = datetime.now(UTC) - timedelta(days=2)
    await _exec(engine, "UPDATE auth.sessions SET last_seen_at = :old", old=old)

    response = await _get(http, token)

    assert response.status_code == 200, response.text
    [(seen,)] = await _exec(engine, "SELECT last_seen_at FROM auth.sessions")
    assert seen > datetime.now(UTC) - timedelta(minutes=1)


async def test_use_within_touch_interval_does_not_write(
    http: httpx.AsyncClient, engine: AsyncEngine, ada: tuple[UUID, str]
) -> None:
    _, token = ada
    recent = datetime.now(UTC) - timedelta(minutes=2)
    await _exec(engine, "UPDATE auth.sessions SET last_seen_at = :at", at=recent)

    response = await _get(http, token)

    assert response.status_code == 200, response.text
    [(seen,)] = await _exec(engine, "SELECT last_seen_at FROM auth.sessions")
    assert seen == recent


# ------------------------------------------------------------------ revocation
async def _revoke(engine: AsyncEngine, redis: Redis, token: str) -> None:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await auth_service.sessions.logout(session, redis, token)
        await session.commit()


@pytest.mark.parametrize("cached", [True, False])
async def test_logout_takes_effect_on_next_request(
    http: httpx.AsyncClient,
    engine: AsyncEngine,
    redis: Redis,
    ada: tuple[UUID, str],
    cached: bool,
) -> None:
    _, token = ada
    if cached:
        assert (await _get(http, token)).status_code == 200
        assert await redis.exists(f"auth:session:{security.hash_session_token(token).hex()}")

    await _revoke(engine, redis, token)

    assert_problem(await _get(http, token), 401, "auth.session_expired")


async def test_logout_of_unknown_token_is_a_no_op(engine: AsyncEngine, redis: Redis) -> None:
    await _revoke(engine, redis, "never-issued")


async def test_logout_all_revokes_every_session_of_the_user_only(
    http: httpx.AsyncClient, engine: AsyncEngine, redis: Redis, ada: tuple[UUID, str]
) -> None:
    ada_id, first = ada
    second = await _new_session(engine, ada_id)
    bob = await _new_session(engine, await _user_id(engine, "google-bob", "bob@x.io"))
    assert (await _get(http, first)).status_code == 200  # cached

    async with AsyncSession(engine, expire_on_commit=False) as session:
        count = await auth_service.sessions.logout_all(session, redis, ada_id)
        await session.commit()

    assert count == 2
    assert_problem(await _get(http, first), 401, "auth.session_expired")
    assert_problem(await _get(http, second), 401, "auth.session_expired")
    assert (await _get(http, bob)).status_code == 200


async def test_stale_cache_write_after_revocation_cannot_revive_the_session(
    http: httpx.AsyncClient, engine: AsyncEngine, redis: Redis, ada: tuple[UUID, str]
) -> None:
    # A request that read the session from Postgres before the logout committed
    # writes it to the cache after the revocation: the tombstone must win.
    _, token = ada
    token_hash = security.hash_session_token(token)
    async with AsyncSession(engine) as session:
        stale = await repo.sessions.get_by_hash(session, token_hash)
    assert isinstance(stale, SessionRecord)

    await _revoke(engine, redis, token)
    await cache.sessions.write(redis, token_hash, stale, datetime.now(UTC))

    assert_problem(await _get(http, token), 401, "auth.session_expired")


# ------------------------------------------------------------------------ CSRF
async def test_mutation_without_client_header_is_403_csrf_failed(
    http: httpx.AsyncClient, ada: tuple[UUID, str]
) -> None:
    _, token = ada

    assert_problem(await _post(http, token), 403, "auth.csrf_failed")
    assert_problem(await _post(http, token, {"X-Metis-Client": "other"}), 403, "auth.csrf_failed")


async def test_mutation_with_web_client_header_is_allowed(
    http: httpx.AsyncClient, ada: tuple[UUID, str]
) -> None:
    user_id, token = ada

    response = await _post(http, token, WEB_CLIENT)

    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == str(user_id)


async def test_mutation_without_cookie_is_not_signed_in_before_csrf(
    http: httpx.AsyncClient,
) -> None:
    assert_problem(await http.post(PROBE), 401, "auth.not_signed_in")


# --------------------------------------------------------------------- storage
async def test_only_the_token_hash_is_stored(engine: AsyncEngine, ada: tuple[UUID, str]) -> None:
    _, token = ada

    [row] = await _exec(engine, "SELECT * FROM auth.sessions")

    assert bytes(row.token_hash) == security.hash_session_token(token)
    assert all(token not in str(value) for value in row)
    assert row.user_agent == "pytest/1.0"
    assert str(row.ip) == "127.0.0.1"
    lifetime = row.expires_at - row.created_at
    assert abs(lifetime - timedelta(days=get_settings().session_ttl_days)) < timedelta(seconds=5)


async def test_raw_token_never_reaches_the_logs(
    http: httpx.AsyncClient, engine: AsyncEngine, redis: Redis
) -> None:
    user_id = await _user_id(engine)
    with capture_logs() as logs:
        token = await _new_session(engine, user_id)
        await _get(http, token)
        await _post(http, token)
        await _revoke(engine, redis, token)
        await _get(http, token)

    assert token not in repr(logs)
    reasons = {e.get("reason") for e in logs if e["event"] == "auth.session_rejected"}
    assert {"csrf", "revoked"} <= reasons


async def test_falls_back_to_postgres_when_redis_is_down(
    http: httpx.AsyncClient, ada: tuple[UUID, str]
) -> None:
    user_id, token = ada
    down: Redis = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    app.dependency_overrides[get_redis] = lambda: down
    try:
        response = await _get(http, token)
    finally:
        await down.aclose()

    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == str(user_id)


# ---------------------------------------------------------------------- cookie
async def test_session_cookie_attributes(http: httpx.AsyncClient) -> None:
    response = await http.post(COOKIE_PROBE)

    header = response.headers["set-cookie"]
    assert header.startswith(f"{COOKIE}=probe-token")
    lowered = header.lower()
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert "path=/" in lowered
    assert f"max-age={get_settings().session_ttl_days * 86_400}" in lowered
    assert "secure" not in lowered  # tests run with APP_ENV=development


async def test_session_cookie_is_secure_when_configured(
    http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    secure = get_settings().model_copy(update={"cookie_secure": True})
    monkeypatch.setattr(security, "get_settings", lambda: secure)

    response = await http.post(COOKIE_PROBE)

    assert "; secure" in response.headers["set-cookie"].lower()


# ------------------------------------------------------------------------ CORS
async def test_cors_preflight_allows_credentials_and_client_header(
    http: httpx.AsyncClient,
) -> None:
    response = await http.options(
        PROBE,
        headers={
            "Origin": WEB_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-metis-client",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WEB_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "x-metis-client" in response.headers["access-control-allow-headers"].lower()


# ------------------------------------------------------------------- migration
async def test_downgrade_restores_auth_sub_from_google_identities(engine: AsyncEngine) -> None:
    google_user = await create_user(engine, "google-ada", "ada@x.io")
    bare = await _exec(
        engine,
        "INSERT INTO auth.users (id, email) VALUES (gen_random_uuid(), 'bare@x.io') RETURNING id",
    )
    bare_id = bare[0][0]

    # DDL is transactional in Postgres: replay the downgrades' SQL, then roll back.
    # 0009's and 0008's downgrades run first: 0007's SQL expects
    # ``identity.auth_identities``.
    async with engine.connect() as conn, conn.begin() as tx:
        for migration in ("0009_rename_auth_identities.py", "0008_auth_schema.py"):
            for statement in load_migration(migration).DOWNGRADE_SQL:
                await conn.execute(text(statement))
        await conn.execute(text("ALTER TABLE identity.users ADD COLUMN auth_sub text"))
        await conn.execute(text(load_migration("0007_drop_users_auth_sub.py").RESTORE_SQL))
        rows = dict((await conn.execute(text("SELECT id, auth_sub FROM identity.users"))).all())
        await tx.rollback()

    assert rows == {google_user: "google-ada", bare_id: f"user:{bare_id}"}
