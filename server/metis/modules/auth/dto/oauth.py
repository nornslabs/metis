"""OAuth DTOs: what a login keeps between redirect and callback, and what it produces."""

from __future__ import annotations

from metis.helpers.dto import FrozenModel


class PendingLogin(FrozenModel):
    """What the callback needs to finish a login (stored in Redis, never logged)."""

    nonce: str
    code_verifier: str
    redirect_to: str


class FinishedLogin(FrozenModel):
    """A completed sign-in: the session token for the cookie and where to go next."""

    token: str
    redirect_to: str
