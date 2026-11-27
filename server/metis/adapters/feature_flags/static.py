"""Feature flags read from environment variables (``FF_<KEY>``), for local runs and CI."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import structlog

from metis.core.ports import FlagContext

_ENV_PREFIX = "FF_"
_TRUE_SPELLINGS = frozenset({"true", "1", "yes", "on"})
_FALSE_SPELLINGS = frozenset({"false", "0", "no", "off"})

logger = structlog.get_logger(__name__)


def _env_name(key: str) -> str:
    """The env var that holds flag ``key``: ``llm_enabled`` -> ``FF_LLM_ENABLED``."""
    return f"{_ENV_PREFIX}{key.upper()}"


class StaticProvider:
    """A ``FeatureFlagProvider`` over a snapshot of ``FF_*`` values.

    Every workspace sees the same value (the context is ignored). Values never appear
    in logs; a malformed one logs its key once and gives the caller's default.
    """

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = {
            name: value for name, value in values.items() if name.startswith(_ENV_PREFIX)
        }
        self._warned: set[str] = set()

    async def is_enabled(self, key: str, context: FlagContext, default: bool = False) -> bool:
        raw = self._raw(key)
        if raw is None:
            return default
        lowered = raw.lower()
        if lowered in _TRUE_SPELLINGS:
            return True
        if lowered in _FALSE_SPELLINGS:
            return False
        self._warn_invalid(key)
        return default

    async def get_string(self, key: str, context: FlagContext, default: str) -> str:
        raw = self._raw(key)
        return default if raw is None else raw

    async def get_json(self, key: str, context: FlagContext, default: Any) -> Any:
        raw = self._raw(key)
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except ValueError:
            self._warn_invalid(key)
            return default

    async def get_experiment_variant(self, key: str, context: FlagContext, default: str) -> str:
        return await self.get_string(key, context, default)

    async def track_event(self, name: str, context: FlagContext) -> None:
        """Nothing is sent anywhere: the static provider has no experiment backend."""
        logger.debug("feature_flags.event_ignored", event=name)

    async def close(self) -> None:
        """Nothing to release."""

    def _raw(self, key: str) -> str | None:
        """The trimmed value of ``key``; ``None`` when unset or empty."""
        value = self._values.get(_env_name(key), "").strip()
        return value or None

    def _warn_invalid(self, key: str) -> None:
        if key in self._warned:
            return
        self._warned.add(key)
        logger.warning("feature_flags.invalid_value", key=key)
