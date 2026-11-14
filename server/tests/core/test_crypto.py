"""Tests for envelope encryption in ``metis.core.crypto``."""

from __future__ import annotations

from base64 import urlsafe_b64encode
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest

from metis.core.config import get_settings
from metis.core.crypto import SealedSecret, decrypt, encrypt, mask
from metis.core.errors import ErrorCode, InvalidInputError, SecretDecryptError

WORKSPACE_ID = UUID("0192f1a0-0000-7000-8000-000000000001")
OTHER_WORKSPACE_ID = UUID("0192f1a0-0000-7000-8000-000000000002")
SECRET = "sk-test-0123456789abcdefa1b2"
UNKNOWN_KEY_VERSION = 999
HTTP_UNPROCESSABLE = 422


def _master_key(fill: bytes) -> str:
    return urlsafe_b64encode(fill * 32).decode()


def _use_master_key(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    monkeypatch.setenv("ENCRYPTION_MASTER_KEY", key)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _flip_first_byte(value: bytes) -> bytes:
    return bytes([value[0] ^ 0x01]) + value[1:]


# ------------------------------------------------------------------ round trip


def test_decrypt_returns_the_encrypted_secret() -> None:
    sealed = encrypt(SECRET, WORKSPACE_ID)

    assert decrypt(sealed, WORKSPACE_ID) == SECRET


def test_round_trip_keeps_non_ascii_secrets() -> None:
    secret = "clé-秘密-🔑"

    assert decrypt(encrypt(secret, WORKSPACE_ID), WORKSPACE_ID) == secret


def test_uuid_and_its_string_form_are_the_same_aad() -> None:
    sealed = encrypt(SECRET, WORKSPACE_ID)

    assert decrypt(sealed, str(WORKSPACE_ID)) == SECRET


def test_sealed_secret_does_not_contain_the_plaintext() -> None:
    sealed = encrypt(SECRET, WORKSPACE_ID)

    for field in (sealed.ciphertext, sealed.nonce, sealed.wrapped_key):
        assert SECRET.encode() not in field


def test_encrypting_the_same_secret_twice_gives_different_output() -> None:
    first = encrypt(SECRET, WORKSPACE_ID)
    second = encrypt(SECRET, WORKSPACE_ID)

    assert first.ciphertext != second.ciphertext
    assert first.nonce != second.nonce
    assert first.wrapped_key != second.wrapped_key


def test_sealed_secret_records_the_current_key_version() -> None:
    assert encrypt(SECRET, WORKSPACE_ID).key_version == 1


def test_sealed_secret_is_immutable() -> None:
    sealed = encrypt(SECRET, WORKSPACE_ID)

    with pytest.raises(ValueError):
        sealed.key_version = 2  # type: ignore[misc]


# -------------------------------------------------------------------- failures


@pytest.mark.parametrize("field", ["ciphertext", "nonce", "wrapped_key"])
def test_tampered_field_fails_to_decrypt(field: str) -> None:
    sealed = encrypt(SECRET, WORKSPACE_ID)
    tampered = sealed.model_copy(update={field: _flip_first_byte(getattr(sealed, field))})

    with pytest.raises(SecretDecryptError):
        decrypt(tampered, WORKSPACE_ID)


def test_truncated_wrapped_key_fails_to_decrypt() -> None:
    sealed = encrypt(SECRET, WORKSPACE_ID)
    truncated = sealed.model_copy(update={"wrapped_key": b"short"})

    with pytest.raises(SecretDecryptError):
        decrypt(truncated, WORKSPACE_ID)


def test_wrong_workspace_fails_to_decrypt() -> None:
    sealed = encrypt(SECRET, WORKSPACE_ID)

    with pytest.raises(SecretDecryptError):
        decrypt(sealed, OTHER_WORKSPACE_ID)


def test_unknown_key_version_fails_to_decrypt() -> None:
    sealed = encrypt(SECRET, WORKSPACE_ID)
    unknown = sealed.model_copy(update={"key_version": UNKNOWN_KEY_VERSION})

    with pytest.raises(SecretDecryptError):
        decrypt(unknown, WORKSPACE_ID)


def test_secret_sealed_under_another_master_key_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_master_key(monkeypatch, _master_key(b"a"))
    sealed = encrypt(SECRET, WORKSPACE_ID)

    _use_master_key(monkeypatch, _master_key(b"b"))

    with pytest.raises(SecretDecryptError):
        decrypt(sealed, WORKSPACE_ID)


def test_decrypt_error_does_not_leak_the_plaintext() -> None:
    sealed = encrypt(SECRET, WORKSPACE_ID)

    with pytest.raises(SecretDecryptError) as exc_info:
        decrypt(sealed, OTHER_WORKSPACE_ID)

    assert SECRET not in str(exc_info.value)
    assert SECRET not in repr(exc_info.value)


def test_decrypt_error_maps_to_422_with_its_code() -> None:
    error = SecretDecryptError()

    assert error.code == ErrorCode.SECRET_DECRYPT_FAILED
    assert error.code == "crypto.decrypt_failed"
    assert error.status == HTTP_UNPROCESSABLE


def test_encrypting_an_empty_secret_is_rejected() -> None:
    with pytest.raises(InvalidInputError):
        encrypt("", WORKSPACE_ID)


def test_non_uuid_aad_is_rejected() -> None:
    with pytest.raises(InvalidInputError):
        encrypt(SECRET, "not-a-workspace-id")


def test_sealed_secret_has_exactly_the_stored_fields() -> None:
    assert set(SealedSecret.model_fields) == {
        "ciphertext",
        "nonce",
        "wrapped_key",
        "key_version",
    }


def test_random_workspace_ids_round_trip() -> None:
    workspace_id = uuid4()

    assert decrypt(encrypt(SECRET, workspace_id), workspace_id) == SECRET


# ------------------------------------------------------------------------ mask


def test_mask_shows_prefix_and_last_four_of_a_long_secret() -> None:
    assert mask("sk-proj-abcdefghijkla1b2") == "sk-…a1b2"


def test_mask_reveals_nothing_else_of_a_long_secret() -> None:
    secret = "sk-proj-abcdefghijkla1b2"
    masked = mask(secret)

    hidden = secret[3:-4]
    assert hidden not in masked
    assert masked.endswith(secret[-4:])


def test_mask_of_a_twelve_char_secret_shows_prefix_and_last_four() -> None:
    assert mask("abcdefghwxyz") == "abc…wxyz"


@pytest.mark.parametrize("secret", ["", "a", "short", "abcdefghijk"])
def test_mask_of_a_short_secret_reveals_nothing(secret: str) -> None:
    masked = mask(secret)

    assert masked == "…••••"
