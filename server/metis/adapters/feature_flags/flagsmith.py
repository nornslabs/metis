"""Feature flags from Flagsmith, evaluated locally from the downloaded environment document."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any, Protocol

import structlog
from flagsmith import Flagsmith
from flagsmith.exceptions import FlagsmithFeatureDoesNotExistError

from metis.core.config import SERVER_KEY_PREFIX
from metis.core.ports import FlagContext

CLIENT_BUILD_COOLDOWN_SECONDS = 30.0
WARNING_INTERVAL_SECONDS = 60.0
MAX_WARNING_KEYS = 1000
ENVIRONMENT_REFRESH_SECONDS = 60

logger = structlog.get_logger(__name__)


class _SdkFlag(Protocol):
    enabled: bool
    value: Any


class _SdkFlags(Protocol):
    def get_flag(self, feature_name: str) -> _SdkFlag: ...


class _SdkClient(Protocol):
    def get_identity_flags(self, identifier: str, traits: dict[str, Any]) -> _SdkFlags: ...

    def get_environment_flags(self) -> _SdkFlags: ...

    def close(self) -> None: ...


ClientFactory = Callable[[], _SdkClient]


class FlagsmithProvider:
    """A ``FeatureFlagProvider`` over the Flagsmith SDK.

    The SDK client is built on the first read, in a thread, because building it downloads
    the environment and starts a refresh thread. Reads never raise: any failure gives the
    caller's default. Values never appear in logs.
    """

    def __init__(
        self,
        environment_key: str,
        api_url: str,
        *,
        client_factory: ClientFactory | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not environment_key.startswith(SERVER_KEY_PREFIX):
            raise ValueError(
                "flagsmith_environment_key must be a server-side key (starts with 'ser.')"
            )
        self._client_factory = client_factory or self._sdk_factory(environment_key, api_url)
        self._clock = clock
        self._client: _SdkClient | None = None
        self._building: asyncio.Task[None] | None = None
        self._closed = False
        self._retry_at = 0.0
        self._last_warning: dict[str, float] = {}
        self._invalid_warned: set[str] = set()

    @staticmethod
    def _sdk_factory(environment_key: str, api_url: str) -> ClientFactory:
        def build() -> _SdkClient:
            return Flagsmith(
                environment_key=environment_key,
                api_url=api_url,
                enable_local_evaluation=True,
                environment_refresh_interval_seconds=ENVIRONMENT_REFRESH_SECONDS,
                enable_analytics=True,
            )

        return build

    async def is_enabled(self, key: str, context: FlagContext, default: bool = False) -> bool:
        flag = await self._flag(key, context)
        return default if flag is None else bool(flag.enabled)

    async def get_string(self, key: str, context: FlagContext, default: str) -> str:
        value = await self._value(key, context)
        if value is None or value == "":
            return default
        return value if isinstance(value, str) else str(value)

    async def get_experiment_variant(self, key: str, context: FlagContext, default: str) -> str:
        """The identity's variation; the read is the exposure (analytics are on)."""
        return await self.get_string(key, context, default)

    async def track_event(self, name: str, context: FlagContext) -> None:
        """Log the conversion. The server SDK has no custom event API, so nothing is sent."""
        logger.info(
            "feature_flags.event_tracked",
            event_name=name,
            workspace_id=None if context.workspace_id is None else str(context.workspace_id),
        )

    async def get_json(self, key: str, context: FlagContext, default: Any) -> Any:
        value = await self._value(key, context)
        if value is None:
            return default
        if not isinstance(value, str):
            return value
        if not value.strip():
            return default
        try:
            return json.loads(value)
        except ValueError:
            if key not in self._invalid_warned:
                self._invalid_warned.add(key)
                logger.warning("feature_flags.invalid_value", key=key)
            return default

    async def close(self) -> None:
        self._closed = True
        if self._building is not None:
            await asyncio.shield(self._building)
        client, self._client = self._client, None
        if client is not None:
            await asyncio.to_thread(client.close)

    async def _value(self, key: str, context: FlagContext) -> Any:
        """The flag's value; ``None`` when it is missing, switched off or has none."""
        flag = await self._flag(key, context)
        if flag is None or not flag.enabled:
            return None
        return flag.value

    async def _flag(self, key: str, context: FlagContext) -> _SdkFlag | None:
        client = await self._ready_client()
        if client is None:
            return None
        try:
            return await asyncio.to_thread(_lookup, client, context, key)
        except Exception as error:
            self._warn("feature_flags.flagsmith_error", key, error=type(error).__name__)
            return None

    async def _ready_client(self) -> _SdkClient | None:
        if self._client is not None:
            return self._client
        if self._closed or self._clock() < self._retry_at:
            return None
        if self._building is None:
            self._building = asyncio.create_task(self._build_client())
        # Shielded: a cancelled reader must not abandon a half-built client.
        await asyncio.shield(self._building)
        return self._client

    async def _build_client(self) -> None:
        try:
            client = await asyncio.to_thread(self._client_factory)
        except Exception as error:
            self._retry_at = self._clock() + CLIENT_BUILD_COOLDOWN_SECONDS
            logger.warning("feature_flags.flagsmith_unavailable", error=type(error).__name__)
        else:
            if self._closed:
                await asyncio.to_thread(client.close)
            else:
                self._client = client
        finally:
            self._building = None

    def _warn(self, event: str, key: str, **fields: str) -> None:
        """Log at most once per key and event per minute."""
        now = self._clock()
        marker = f"{event}:{key}"
        last = self._last_warning.get(marker)
        if last is not None and now - last < WARNING_INTERVAL_SECONDS:
            return
        if len(self._last_warning) >= MAX_WARNING_KEYS:
            self._last_warning.clear()
        self._last_warning[marker] = now
        logger.warning(event, key=key, **fields)


def _identity(context: FlagContext) -> str | None:
    """Workspace first, then user; ``None`` reads the environment-level flags."""
    if context.workspace_id is not None:
        return str(context.workspace_id)
    if context.user_id is not None:
        return str(context.user_id)
    return None


def _traits(context: FlagContext) -> dict[str, Any]:
    traits: dict[str, Any] = {**context.custom_attributes, "environment": context.environment}
    if context.user_id is not None:
        traits["user_id"] = str(context.user_id)
    return traits


def _lookup(client: _SdkClient, context: FlagContext, key: str) -> _SdkFlag | None:
    """The flag for ``key``, or ``None`` when it does not exist. Blocking: run in a thread."""
    identity = _identity(context)
    flags = (
        client.get_environment_flags()
        if identity is None
        else client.get_identity_flags(identity, _traits(context))
    )
    try:
        return flags.get_flag(key)
    except FlagsmithFeatureDoesNotExistError:
        return None
