"""String clean-up for Pydantic ``BeforeValidator``s; non-strings pass through."""

from __future__ import annotations

from typing import overload


def strip(value: object) -> object:
    """Trim surrounding whitespace."""
    return value.strip() if isinstance(value, str) else value


def strip_to_none(value: object) -> object:
    """Trim; a blank string means "not provided" and becomes ``None``."""
    return (value.strip() or None) if isinstance(value, str) else value


@overload
def normalise_email(value: str) -> str: ...
@overload
def normalise_email(value: object) -> object: ...
def normalise_email(value: object) -> object:
    """Trim and lowercase, so the same address always compares equal.

    A ``str`` comes back as a ``str``; anything else passes through, so it also
    works as a ``BeforeValidator``.
    """
    return value.strip().lower() if isinstance(value, str) else value
