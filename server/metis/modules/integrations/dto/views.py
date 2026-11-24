"""Response and request bodies of the integrations routes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import Field

from metis.adapters.mcp.linear import ToolInfo
from metis.helpers.dto import FrozenModel
from metis.modules.integrations.dto.providers import IntegrationProvider, IntegrationStatus

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

MAX_REDIRECT_TO_LENGTH = 2048


class IntegrationView(FrozenModel):
    """One provider's connection as members see it. Never carries a token or a secret."""

    provider: IntegrationProvider
    status: IntegrationStatus
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    connected_at: datetime | None = None
    connected_by: UUID | None = None
    version: int = 0


class IntegrationList(FrozenModel):
    items: list[IntegrationView]


class ConnectRequest(FrozenModel):
    """Body of ``POST /v1/integrations/{provider}/connect``."""

    redirect_to: Annotated[str | None, Field(max_length=MAX_REDIRECT_TO_LENGTH)] = None


class ConnectStarted(FrozenModel):
    authorize_url: str


class ToolList(FrozenModel):
    items: list[ToolInfo]
