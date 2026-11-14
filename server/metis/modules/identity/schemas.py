"""Identity input models, DTOs returned by ``service.py``, ``MemberRole`` and ``ProviderKind``."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    ValidationInfo,
    field_validator,
    model_validator,
)

from metis.helpers.text import strip, strip_to_none

MAX_NAME_LENGTH = 200
MAX_EMAIL_LENGTH = 320
MAX_WORKSPACE_NAME_LENGTH = 100
# Shape check only: claims come from a verified identity provider.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
IMAGE_URL_SCHEMES = ("https://", "http://")

MAX_KEY_LENGTH = 512
MAX_MODEL_LENGTH = 200
MAX_BASE_URL_LENGTH = 2048
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# Validation context flag: allow http:// base URLs on LOCAL_HOSTS (development only).
ALLOW_LOCAL_HTTP = "allow_local_http"

DEFAULT_RUN_BUDGET_USD = Decimal("2.00")
DEFAULT_MAX_STEPS = 50
MAX_RUN_BUDGET_USD = Decimal("100")
MAX_MAX_STEPS = 200
USD_DECIMAL_PLACES = 2


class MemberRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class ProviderKind(StrEnum):
    LLM = "llm"
    EXA = "exa"


def _normalise_email(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value


def _check_email_shape(value: str) -> str:
    if not re.fullmatch(EMAIL_PATTERN, value):
        raise ValueError("must be an email address")
    return value


def _check_image_url(value: str | None) -> str | None:
    if value is not None and not value.lower().startswith(IMAGE_URL_SCHEMES):
        raise ValueError("must be an http(s) URL")
    return value


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


Email = Annotated[
    str,
    BeforeValidator(_normalise_email),
    Field(max_length=MAX_EMAIL_LENGTH),
    AfterValidator(_check_email_shape),
]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)


class UserClaims(_Frozen):
    """Sign-in claims from a verified token, validated and normalised."""

    sub: Annotated[str, BeforeValidator(strip), Field(min_length=1)]
    email: Email
    name: Annotated[
        Annotated[str, Field(max_length=MAX_NAME_LENGTH)] | None,
        BeforeValidator(strip_to_none),
    ] = None
    image: Annotated[
        str | None, BeforeValidator(strip_to_none), AfterValidator(_check_image_url)
    ] = None


class WorkspaceName(_Frozen):
    name: Annotated[
        str, BeforeValidator(strip), Field(min_length=1, max_length=MAX_WORKSPACE_NAME_LENGTH)
    ]


class NewMember(_Frozen):
    email: Email
    role: MemberRole


class NewProviderKey(_Frozen):
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


UsdAmount = Annotated[
    Decimal,
    Field(gt=0, le=MAX_RUN_BUDGET_USD, decimal_places=USD_DECIMAL_PLACES),
    PlainSerializer(float, return_type=float),
]
StepCount = Annotated[int, Field(ge=1, le=MAX_MAX_STEPS)]


class SettingsPatch(_Frozen):
    """Body of ``PATCH /v1/settings``: the ``version`` read, plus at least one change."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Annotated[int, Field(ge=0)]
    run_budget_usd: UsdAmount | None = None
    max_steps: StepCount | None = None

    @model_validator(mode="after")
    def _has_a_change(self) -> Self:
        if self.run_budget_usd is None and self.max_steps is None:
            raise ValueError("give run_budget_usd or max_steps")
        return self


class User(_Frozen):
    id: UUID
    email: str
    name: str | None
    image: str | None
    created_at: datetime


class Workspace(_Frozen):
    id: UUID
    name: str
    is_personal: bool
    created_by: UUID
    created_at: datetime


class Membership(_Frozen):
    workspace: Workspace
    role: MemberRole


# --------------------------------------------------------------- HTTP schemas
class CreateWorkspaceRequest(_Frozen):
    """Body of ``POST /v1/workspaces``; the service validates and trims ``name``."""

    name: str


class MeResponse(_Frozen):
    user: User
    workspaces: list[Membership]
    current_workspace: Membership


class MembershipPage(_Frozen):
    items: list[Membership]
    next_cursor: str | None = None


class PutProviderKeyRequest(_Frozen):
    """Body of ``PUT /v1/settings/keys/{kind}``; the service validates it."""

    value: str
    base_url: str | None = None
    model: str | None = None


class ProviderKeyView(_Frozen):
    """A saved key as clients see it: masked, never the plaintext or ciphertext."""

    kind: ProviderKind
    base_url: str | None
    model: str | None
    masked: str
    last_tested_at: datetime | None
    last_test_ok: bool | None
    version: int
    updated_at: datetime


class ProviderKeys(_Frozen):
    llm: ProviderKeyView | None = None
    exa: ProviderKeyView | None = None


class WorkspaceSettingsView(_Frozen):
    """Run limits; ``version`` 0 means defaults that were never saved."""

    run_budget_usd: UsdAmount
    max_steps: int
    version: int


class SettingsResponse(_Frozen):
    keys: ProviderKeys
    settings: WorkspaceSettingsView


class ProviderCredentials(_Frozen):
    """A decrypted key for the LLM gateway and Exa adapter only; never log or return it."""

    kind: ProviderKind
    api_key: str = Field(repr=False)
    base_url: str | None
    model: str | None
