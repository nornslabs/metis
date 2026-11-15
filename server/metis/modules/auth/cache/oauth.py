"""OAuth login state: ``auth:oauth:{state}`` holds a ``PendingLogin`` for :data:`STATE_TTL_SECONDS`
and is taken back with ``GETDEL`` (single use).

Redis errors propagate: without the state a sign-in cannot finish, so ``service`` turns
them into ``OAuthFailedError``. Values are never logged.
"""

from __future__ import annotations

from pydantic import ValidationError
from redis.asyncio import Redis

from metis.core.logging import get_logger
from metis.modules.auth.dto import PendingLogin

KEY_PREFIX = "auth:oauth:"
STATE_TTL_SECONDS = 600


def key(state: str) -> str:
    """Redis key of the pending login started with ``state``."""
    return f"{KEY_PREFIX}{state}"


async def save_pending(redis: Redis, state: str, pending: PendingLogin) -> None:
    """Remember ``pending`` for :data:`STATE_TTL_SECONDS`; raises ``RedisError``."""
    await redis.set(key(state), pending.model_dump_json(), ex=STATE_TTL_SECONDS)


async def take_pending(redis: Redis, state: str) -> PendingLogin | None:
    """Take back (single use) the login ``state`` started; ``None`` if unknown or corrupt.

    Raises ``RedisError`` when Redis is unavailable.
    """
    stored = await redis.getdel(key(state))
    if stored is None:
        return None
    try:
        return PendingLogin.model_validate_json(stored)
    except ValidationError:
        logger.warning("auth.oauth_state_corrupt")
        return None


logger = get_logger(__name__)
