"""Identity DTOs returned by ``service.py``, and the ``MemberRole`` enum."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_NAME_LENGTH = 200
MAX_EMAIL_LENGTH = 320
MAX_WORKSPACE_NAME_LENGTH = 100
# Shape check only: claims come from a verified identity provider.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class MemberRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)


class UserClaims(_Frozen):
    """Sign-in claims from a verified token, validated and normalised."""

    sub: str = Field(min_length=1)
    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    image: str | None = None

    @field_validator("sub", "name", "image", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("email", mode="before")
    @classmethod
    def _normalise_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def _check_email_shape(cls, value: str) -> str:
        if not re.fullmatch(EMAIL_PATTERN, value):
            raise ValueError("must be an email address")
        return value


class WorkspaceName(_Frozen):
    name: str = Field(min_length=1, max_length=MAX_WORKSPACE_NAME_LENGTH)

    @field_validator("name", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


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
