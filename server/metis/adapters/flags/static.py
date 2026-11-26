"""Static feature flags: each flag reads an environment variable ``FF_<FLAG>``.

A flag is on when its variable is set to a truthy value (``1``, ``true``, ``yes``,
``on``, case-insensitive); anything else -- missing or empty -- is off. Flags never
change during a run, so a provider instance can be shared across the run's gateway.
"""

from __future__ import annotations

import os

from metis.core.ports import FeatureFlags, FlagContext

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def _flag_env_name(flag: str) -> str:
    return f"FF_{flag.upper()}"


class StaticProvider:
    """Feature flags that are fixed for a whole run, sourced from the environment.

    A flag is on by default (the kill switch is not tripped); it is off only when its
    ``FF_<FLAG>`` variable is explicitly set to a falsy value (``0``, ``false``, ``no``,
    ``off``). A truthy value (``1``, ``true``, ``yes``, ``on``) also counts as on. Any
    other value -- including an unset variable -- leaves the flag on, so the gateway
    keeps working unless an operator explicitly flips the switch.
    """

    async def is_enabled(self, flag: str, context: FlagContext) -> bool:
        value = os.environ.get(_flag_env_name(flag), "").strip().lower()
        if value in _TRUTHY:
            return True
        if value in _FALSY:
            return False
        return True


def build_flag_provider() -> FeatureFlags:
    """The default feature flag provider: a :class:`StaticProvider`."""
    return StaticProvider()


__all__ = ["StaticProvider", "build_flag_provider"]
