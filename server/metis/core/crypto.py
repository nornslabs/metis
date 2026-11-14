"""Envelope encryption for workspace secrets (BYO provider keys, MCP tokens).

Each secret gets its own random data key. The secret is encrypted with the data
key (AES-256-GCM), and the data key is encrypted ("wrapped") with the master key
for ``key_version``. The workspace id is bound to both layers as additional
authenticated data, so a sealed secret cannot be opened in another workspace.

Nothing in this module logs plaintext or key material.
"""

from __future__ import annotations

import os
from base64 import urlsafe_b64decode
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict

from metis.core.config import get_settings
from metis.core.errors import InvalidInputError, SecretDecryptError

DATA_KEY_BYTES = 32
NONCE_BYTES = 12
CURRENT_KEY_VERSION = 1
KEY_VERSION_BYTES = 4

MASK_MIN_LENGTH = 12
MASK_PREFIX_CHARS = 3
MASK_SUFFIX_CHARS = 4
MASK_ELLIPSIS = "…"
MASK_HIDDEN = "••••"

_DECRYPT_FAILED_DETAIL = "A stored secret could not be read. Please re-enter it."


class SealedSecret(BaseModel):
    """An encrypted secret, exactly as it is stored."""

    model_config = ConfigDict(frozen=True)

    ciphertext: bytes
    nonce: bytes
    wrapped_key: bytes
    key_version: int


def encrypt(plaintext: str, aad: str | UUID) -> SealedSecret:
    """Seal ``plaintext`` for the workspace ``aad`` under the current master key."""
    if not plaintext:
        raise InvalidInputError("Secret must not be empty")
    workspace = _workspace_bytes(aad)

    data_key = AESGCM.generate_key(bit_length=DATA_KEY_BYTES * 8)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(data_key).encrypt(nonce, plaintext.encode(), workspace)

    master = AESGCM(_master_key(CURRENT_KEY_VERSION))
    wrap_nonce = os.urandom(NONCE_BYTES)
    wrap_aad = _wrap_aad(workspace, CURRENT_KEY_VERSION)
    wrapped_key = wrap_nonce + master.encrypt(wrap_nonce, data_key, wrap_aad)

    return SealedSecret(
        ciphertext=ciphertext,
        nonce=nonce,
        wrapped_key=wrapped_key,
        key_version=CURRENT_KEY_VERSION,
    )


def decrypt(sealed: SealedSecret, aad: str | UUID) -> str:
    """Open ``sealed`` for the workspace ``aad``.

    Raises:
        SecretDecryptError: wrong workspace, tampered or malformed fields, or an
            unknown ``key_version``.
    """
    workspace = _workspace_bytes(aad)
    try:
        master = AESGCM(_master_key(sealed.key_version))
        wrap_nonce = sealed.wrapped_key[:NONCE_BYTES]
        wrapped = sealed.wrapped_key[NONCE_BYTES:]
        wrap_aad = _wrap_aad(workspace, sealed.key_version)
        data_key = master.decrypt(wrap_nonce, wrapped, wrap_aad)
        plaintext = AESGCM(data_key).decrypt(sealed.nonce, sealed.ciphertext, workspace)
        return plaintext.decode()
    except (InvalidTag, ValueError, KeyError):
        # Chain nothing: the cause may describe key material.
        raise SecretDecryptError(_DECRYPT_FAILED_DETAIL) from None


def mask(secret: str) -> str:
    """Return a display form such as ``sk-…a1b2``; short secrets reveal nothing."""
    if len(secret) < MASK_MIN_LENGTH:
        return MASK_ELLIPSIS + MASK_HIDDEN
    return secret[:MASK_PREFIX_CHARS] + MASK_ELLIPSIS + secret[-MASK_SUFFIX_CHARS:]


def _master_key(key_version: int) -> bytes:
    """Return the master key for ``key_version``; ``KeyError`` if unknown."""
    keyring = {CURRENT_KEY_VERSION: get_settings().encryption_master_key}
    return urlsafe_b64decode(keyring[key_version])


def _workspace_bytes(aad: str | UUID) -> bytes:
    """Encode the workspace id canonically, so a UUID and its string match."""
    try:
        workspace_id = aad if isinstance(aad, UUID) else UUID(aad)
    except ValueError:
        raise InvalidInputError("Workspace id must be a UUID") from None
    return workspace_id.bytes


def _wrap_aad(workspace: bytes, key_version: int) -> bytes:
    """Bind the wrapped data key to its workspace and master-key version."""
    return workspace + key_version.to_bytes(KEY_VERSION_BYTES, "big")
