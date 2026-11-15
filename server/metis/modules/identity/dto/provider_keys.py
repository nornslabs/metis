"""Provider key DTOs: new keys, what is shown back (masked), and credentials for use."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self
from urllib.parse import urlsplit

from pydantic import BeforeValidator, Field, ValidationInfo, field_validator, model_validator

from metis.helpers.dto import FrozenModel
from metis.helpers.text import strip, strip_to_none

MAX_KEY_LENGTH = 512
MAX_MODEL_LENGTH = 200
MAX_BASE_URL_LENGTH = 2048
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# Validation context flag: allow http:// base URLs on LOCAL_HOSTS (development only).
ALLOW_LOCAL_HTTP = "allow_local_http"


class ProviderKind(StrEnum):
    LLM = "llm"
    EXA = "exa"


def _check_base_url(value: str, allow_local_http: bool) -> str:
    """Accept an https URL (or local http in development); drop a trailing slash."""
    parts = urlsplit(value)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise ValueError("must be an http(s) URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("must not contain credentials, a query or a fragment")
    if parts.scheme == "http" and not (allow_local_http and parts.hostname in LOCAL_HOSTS):
        raise ValueError("must use https (http only for localhost in development)")
    return value.rstrip("/")


class NewProviderKey(FrozenModel):
    """A key to save. Validate with context ``{ALLOW_LOCAL_HTTP: bool}``.

    ``llm`` needs ``base_url`` and ``model``; ``exa`` takes neither.
    """

    kind: ProviderKind
    value: Annotated[str, BeforeValidator(strip), Field(min_length=1, max_length=MAX_KEY_LENGTH)]
    base_url: Annotated[
        Annotated[str, Field(max_length=MAX_BASE_URL_LENGTH)] | None,
        BeforeValidator(strip_to_none),
    ] = None
    model: Annotated[
        Annotated[str, Field(min_length=1, max_length=MAX_MODEL_LENGTH)] | None,
        BeforeValidator(strip),
    ] = None

    @field_validator("base_url")
    @classmethod
    def _base_url(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        allow_local_http = bool((info.context or {}).get(ALLOW_LOCAL_HTTP, False))
        return _check_base_url(value, allow_local_http)

    @model_validator(mode="after")
    def _fields_match_kind(self) -> Self:
        needs_endpoint = self.kind is ProviderKind.LLM
        has = (self.base_url is not None, self.model is not None)
        if needs_endpoint and not all(has):
            raise ValueError("an llm key needs base_url and model")
        if not needs_endpoint and any(has):
            raise ValueError("an exa key takes no base_url or model")
        return self


class PutProviderKeyRequest(FrozenModel):
    """Body of ``PUT /v1/settings/keys/{kind}``; the service validates it."""

    value: str
    base_url: str | None = None
    model: str | None = None


class ProviderKeyView(FrozenModel):
    """A saved key as clients see it: masked, never the plaintext or ciphertext."""

    kind: ProviderKind
    base_url: str | None
    model: str | None
    masked: str
    last_tested_at: datetime | None
    last_test_ok: bool | None
    version: int
    updated_at: datetime


class ProviderKeys(FrozenModel):
    llm: ProviderKeyView | None = None
    exa: ProviderKeyView | None = None


class ProviderCredentials(FrozenModel):
    """A decrypted key for the LLM gateway and Exa adapter only; never log or return it."""

    kind: ProviderKind
    api_key: str = Field(repr=False)
    base_url: str | None
    model: str | None
