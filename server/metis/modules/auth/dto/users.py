"""User DTOs: verified sign-in claims and the user as other code sees them."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BeforeValidator, Field

from metis.helpers.dto import Email, FrozenModel
from metis.helpers.text import strip_to_none

MAX_NAME_LENGTH = 200
IMAGE_URL_SCHEMES = ("https://", "http://")


def _check_image_url(value: str | None) -> str | None:
    if value is not None and not value.lower().startswith(IMAGE_URL_SCHEMES):
        raise ValueError("must be an http(s) URL")
    return value


class UserClaims(FrozenModel):
    """A new user's profile from a verified sign-in, validated and normalised."""

    email: Email
    name: Annotated[
        Annotated[str, Field(max_length=MAX_NAME_LENGTH)] | None,
        BeforeValidator(strip_to_none),
    ] = None
    image: Annotated[
        str | None, BeforeValidator(strip_to_none), AfterValidator(_check_image_url)
    ] = None


class User(FrozenModel):
    id: UUID
    email: str
    name: str | None
    image: str | None
    created_at: datetime
