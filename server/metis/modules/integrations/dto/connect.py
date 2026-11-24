"""The OAuth connect round trip: what Redis holds between connect and callback."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from metis.helpers.dto import FrozenModel
from metis.modules.integrations.dto.providers import IntegrationProvider


class PendingConnect(FrozenModel):
    """A started connect attempt, kept in Redis under its ``state`` until the callback.

    The registered client's secret is sealed (workspace id as AAD) before it reaches Redis.
    """

    workspace_id: UUID
    user_id: UUID
    provider: IntegrationProvider
    client_id: str
    sealed_client_secret: dict[str, Any] | None
    token_endpoint: str
    revocation_endpoint: str | None
    code_verifier: str
    redirect_to: str
    scopes: list[str]


class ConnectResult(FrozenModel):
    """Where to send the browser after a successful connect."""

    provider: IntegrationProvider
    redirect_to: str
