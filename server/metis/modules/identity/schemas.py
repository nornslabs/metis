"""Identity input models, DTOs returned by ``service.py``, and ``MemberRole``."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field

MAX_NAME_LENGTH = 200
MAX_EMAIL_LENGTH = 320
MAX_WORKSPACE_NAME_LENGTH = 100
# Shape check only: claims come from a verified identity provider.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
IMAGE_URL_SCHEMES = ("https://", "http://")


class MemberRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _strip_to_none(value: object) -> object:
    """Blank optional claims mean "not provided"."""
    return (value.strip() or None) if isinstance(value, str) else value


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

    sub: Annotated[str, BeforeValidator(_strip), Field(min_length=1)]
    email: Email
    name: Annotated[
        Annotated[str, Field(max_length=MAX_NAME_LENGTH)] | None,
        BeforeValidator(_strip_to_none),
    ] = None
    image: Annotated[
        str | None, BeforeValidator(_strip_to_none), AfterValidator(_check_image_url)
    ] = None


class WorkspaceName(_Frozen):
    name: Annotated[
        str, BeforeValidator(_strip), Field(min_length=1, max_length=MAX_WORKSPACE_NAME_LENGTH)
    ]


class NewMember(_Frozen):
    email: Email
    role: MemberRole


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
