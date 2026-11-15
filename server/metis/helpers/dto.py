"""Shared Pydantic building blocks: a frozen base model and an ``Email`` field type."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field

from metis.helpers.text import normalise_email

MAX_EMAIL_LENGTH = 320
# Shape check only: deliverability is not checked.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def check_email_shape(value: str) -> str:
    """Accept ``value`` if it looks like ``local@domain.tld``."""
    if not re.fullmatch(EMAIL_PATTERN, value):
        raise ValueError("must be an email address")
    return value


Email = Annotated[
    str,
    BeforeValidator(normalise_email),
    Field(max_length=MAX_EMAIL_LENGTH),
    AfterValidator(check_email_shape),
]


class FrozenModel(BaseModel):
    """Immutable model that can also be built from ORM rows (``from_attributes``)."""

    model_config = ConfigDict(frozen=True, from_attributes=True)
