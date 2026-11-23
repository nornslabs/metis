"""Sealing a connection's tokens and registered client as one secret.

The secret is JSON, encrypted with the workspace id as AAD (``core.crypto``), so a sealed
value cannot be opened in another workspace. Nothing here logs.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from metis.core import crypto
from metis.core.errors import SecretDecryptError

_UNREADABLE = "A stored connection could not be read. Please reconnect."


class StoredTokens(BaseModel):
    """What a connection needs to call its server and refresh itself."""

    model_config = ConfigDict(frozen=True)

    access_token: SecretStr
    refresh_token: SecretStr | None = None
    client_id: str
    client_secret: SecretStr | None = None
    token_endpoint: str
    revocation_endpoint: str | None = None


def seal_tokens(tokens: StoredTokens, workspace_id: UUID) -> dict[str, Any]:
    """The storage form (JSONB) of ``tokens``, sealed for ``workspace_id``."""
    return crypto.seal_to_json(crypto.encrypt(_reveal(tokens), workspace_id))


def open_tokens(stored: dict[str, Any], workspace_id: UUID) -> StoredTokens:
    """Open a value made by ``seal_tokens``; ``SecretDecryptError`` if it cannot be read."""
    plain = crypto.decrypt(crypto.seal_from_json(stored), workspace_id)
    try:
        return StoredTokens.model_validate_json(plain)
    except ValidationError:
        raise SecretDecryptError(_UNREADABLE) from None


def seal_text(value: str, workspace_id: UUID) -> dict[str, Any]:
    """Seal one secret string for ``workspace_id``."""
    return crypto.seal_to_json(crypto.encrypt(value, workspace_id))


def open_text(stored: dict[str, Any], workspace_id: UUID) -> str:
    """Open a value made by ``seal_text``."""
    return crypto.decrypt(crypto.seal_from_json(stored), workspace_id)


def _reveal(tokens: StoredTokens) -> str:
    return json.dumps(
        {
            "access_token": tokens.access_token.get_secret_value(),
            "refresh_token": (
                tokens.refresh_token.get_secret_value() if tokens.refresh_token else None
            ),
            "client_id": tokens.client_id,
            "client_secret": (
                tokens.client_secret.get_secret_value() if tokens.client_secret else None
            ),
            "token_endpoint": tokens.token_endpoint,
            "revocation_endpoint": tokens.revocation_endpoint,
        }
    )
