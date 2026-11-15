"""OAuth login state in ``auth.cache``: saved with a TTL, taken back once, corrupt is a miss."""

from __future__ import annotations

from redis.asyncio import Redis

from metis.modules.auth import cache
from metis.modules.auth.schemas import PendingLogin

PENDING = PendingLogin(nonce="n", code_verifier="v", redirect_to="/ideas")


async def test_saved_pending_login_is_taken_back_once(redis: Redis) -> None:
    await cache.save_pending_login(redis, "state-1", PENDING)

    first = await cache.take_pending_login(redis, "state-1")
    second = await cache.take_pending_login(redis, "state-1")

    assert first == PENDING
    assert second is None


async def test_pending_login_expires_after_state_ttl(redis: Redis) -> None:
    await cache.save_pending_login(redis, "state-2", PENDING)

    ttl = await redis.ttl(cache.oauth_key("state-2"))

    assert 0 < ttl <= cache.OAUTH_STATE_TTL_SECONDS


async def test_unknown_state_is_a_miss(redis: Redis) -> None:
    assert await cache.take_pending_login(redis, "never-saved") is None


async def test_corrupt_pending_login_is_a_miss_and_is_removed(redis: Redis) -> None:
    await redis.set(cache.oauth_key("state-3"), b"not json")

    taken = await cache.take_pending_login(redis, "state-3")

    assert taken is None
    assert await redis.exists(cache.oauth_key("state-3")) == 0
