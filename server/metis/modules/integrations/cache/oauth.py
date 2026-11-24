"""Connect state: ``integrations:oauth:{state}`` holds a ``PendingConnect`` for
:data:`STATE_TTL_SECONDS` and is taken back with ``GETDEL`` (single use).

Redis errors propagate: without the state a connect cannot finish, so ``service`` turns them
into ``IntegrationOAuthFailedError``. Values are never logged.
"""

from __future__ import annotations

from pydantic import ValidationError
from redis.asyncio import Redis

from metis.core.logging import get_logger
from metis.modules.integrations.dto import PendingConnect

KEY_PREFIX = "integrations:oauth:"
STATE_TTL_SECONDS = 600

logger = get_logger(__name__)


def key(state: str) -> str:
    """Redis key of the connect attempt started with ``state``."""
    return f"{KEY_PREFIX}{state}"


async def save_pending(redis: Redis, state: str, pending: PendingConnect) -> None:
    """Remember ``pending`` for :data:`STATE_TTL_SECONDS`; raises ``RedisError``."""
    await redis.set(key(state), pending.model_dump_json(), ex=STATE_TTL_SECONDS)


async def take_pending(redis: Redis, state: str) -> PendingConnect | None:
    """Take back (single use) the attempt ``state`` started; ``None`` if unknown or corrupt.

    Raises ``RedisError`` when Redis is unavailable.
    """
    stored = await redis.getdel(key(state))
    if stored is None:
        return None
    try:
        return PendingConnect.model_validate_json(stored)
    except ValidationError:
        logger.warning("integration.oauth_state_corrupt")
        return None
