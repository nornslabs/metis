"""Shared wording: a provider's display name and the error for a lapsed connection."""

from __future__ import annotations

from metis.core.errors import IntegrationExpiredError
from metis.modules.integrations.dto import IntegrationProvider


def provider_label(provider: IntegrationProvider) -> str:
    return provider.value.capitalize()


def expired_error(provider: IntegrationProvider) -> IntegrationExpiredError:
    """The error for a connection whose tokens no longer work."""
    return IntegrationExpiredError(
        f"The {provider_label(provider)} connection expired. Reconnect it in Settings.",
        meta={"provider": provider.value},
    )
