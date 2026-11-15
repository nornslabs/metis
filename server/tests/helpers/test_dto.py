"""Shared Pydantic building blocks in ``metis.helpers.dto``."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from metis.helpers.dto import MAX_EMAIL_LENGTH, Email, FrozenModel


class _Contact(FrozenModel):
    email: Email


class _Row:
    email = "row@example.com"


def test_email_is_trimmed_and_lowercased() -> None:
    assert _Contact(email="  Ada@Example.COM ").email == "ada@example.com"


@pytest.mark.parametrize("raw", ["not-an-email", "a@b", "a b@example.com", ""])
def test_email_rejects_values_that_are_not_shaped_like_an_address(raw: str) -> None:
    with pytest.raises(ValidationError, match="must be an email address"):
        _Contact(email=raw)


def test_email_rejects_addresses_over_the_length_limit() -> None:
    too_long = "a" * MAX_EMAIL_LENGTH + "@example.com"

    with pytest.raises(ValidationError, match="at most 320"):
        _Contact(email=too_long)


def test_frozen_model_cannot_be_changed_after_creation() -> None:
    contact = _Contact(email="ada@example.com")

    with pytest.raises(ValidationError, match="frozen"):
        contact.email = "bob@example.com"  # type: ignore[misc]


def test_frozen_model_builds_from_attributes() -> None:
    assert _Contact.model_validate(_Row()).email == "row@example.com"


def test_frozen_model_is_a_pydantic_model() -> None:
    assert issubclass(FrozenModel, BaseModel)
