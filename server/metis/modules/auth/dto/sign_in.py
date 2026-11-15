"""Sign-in DTOs: the user a provider profile signed in as, and how they were found."""

from __future__ import annotations

from enum import StrEnum

from metis.helpers.dto import FrozenModel
from metis.modules.auth.dto.users import User


class SignInOutcome(StrEnum):
    """How a sign-in found its user (logged as ``outcome``)."""

    CREATED = "created"
    EXISTING = "existing"
    LINKED = "linked"


class SignedIn(FrozenModel):
    """The user a provider profile signed in as, and how they were found."""

    user: User
    outcome: SignInOutcome
