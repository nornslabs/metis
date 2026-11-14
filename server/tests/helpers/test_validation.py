"""``validate_input``: Pydantic models from untrusted input, safe 422 on failure."""

from __future__ import annotations

from typing import Annotated

import pytest
from pydantic import BaseModel, Field, ValidationInfo, field_validator

from metis.core.errors import InvalidInputError
from metis.helpers.validation import validate_input

SECRET = "sk-very-secret-value"


class _Key(BaseModel):
    value: Annotated[str, Field(max_length=5)]
    model: str | None = None

    @field_validator("model")
    @classmethod
    def _needs_flag(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is not None and not (info.context or {}).get("allow_model"):
            raise ValueError("model not allowed")
        return value


def test_returns_the_model_for_valid_input() -> None:
    assert validate_input(_Key, value="abc") == _Key(value="abc")


def test_invalid_input_is_a_422_with_fields_but_never_the_input() -> None:
    with pytest.raises(InvalidInputError) as caught:
        validate_input(_Key, value=SECRET)

    assert caught.value.status == 422
    assert caught.value.errors is not None
    assert caught.value.errors[0]["field"] == "value"
    assert SECRET not in repr(caught.value.errors)


def test_context_reaches_validators() -> None:
    with pytest.raises(InvalidInputError):
        validate_input(_Key, None, value="abc", model="m")

    assert validate_input(_Key, {"allow_model": True}, value="abc", model="m").model == "m"


def test_a_field_named_model_does_not_clash_with_the_model_argument() -> None:
    assert validate_input(_Key, {"allow_model": True}, value="a", model="gpt").model == "gpt"
