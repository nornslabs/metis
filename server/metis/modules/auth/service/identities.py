"""Sign in (or sign up) the user a verified provider profile vouches for.

``sign_in`` turns a profile into a user: by ``(provider, subject)``, else by the same
email (linking a new identity), else a new user. The personal workspace is not made here:
identity creates it on the user's first workspace-scoped call. Takes the caller's
``AsyncSession`` and never commits.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import EmailUnverifiedError, InvalidInputError
from metis.core.logging import get_logger
from metis.helpers.time import utcnow
from metis.helpers.validation import validate_input
from metis.modules.auth import repo
from metis.modules.auth.dto import SignedIn, SignInOutcome, User, UserClaims
from metis.modules.auth.models import UserRow
from metis.modules.auth.providers.base import OAuthFailure, OAuthStep, ProviderProfile, oauth_failed

# A concurrent first sign-in can win a unique constraint once; the retry finds its rows.
MAX_SIGN_IN_ATTEMPTS = 2


async def sign_in(session: AsyncSession, profile: ProviderProfile) -> SignedIn:
    """Sign in (or sign up) the user ``profile`` vouches for; the email must be verified."""
    if not profile.email_verified:
        logger.info("auth.sign_in_refused", provider=profile.provider, reason="email_unverified")
        raise EmailUnverifiedError("Your email address is not verified with the provider")
    claims = _claims(profile)
    for _ in range(MAX_SIGN_IN_ATTEMPTS):
        # A lost race must not leave a half-made user behind: undo the whole attempt.
        attempt = await session.begin_nested()
        signed_in = await _try_sign_in(session, profile, claims, utcnow())
        if signed_in is None:
            await attempt.rollback()
            continue
        await attempt.commit()
        logger.info(
            "auth.sign_in",
            provider=profile.provider,
            outcome=signed_in.outcome.value,
            user_id=str(signed_in.user.id),
        )
        return signed_in
    raise oauth_failed(profile.provider, OAuthStep.SIGN_IN, OAuthFailure.SIGN_IN_CONFLICT)


logger = get_logger(__name__)


def _claims(profile: ProviderProfile) -> UserClaims:
    """Validate the profile like any user input; a malformed one fails the sign-in."""
    try:
        return validate_input(
            UserClaims,
            email=profile.email,
            name=profile.name,
            image=profile.avatar_url,
        )
    except InvalidInputError:
        raise oauth_failed(profile.provider, OAuthStep.SIGN_IN, OAuthFailure.BAD_RESPONSE) from None


async def _user_for(
    session: AsyncSession, claims: UserClaims
) -> tuple[UserRow, SignInOutcome] | None:
    """The user to link this new identity to, creating one if needed; ``None`` on a race."""
    linked = await repo.users.get_by_email(session, claims.email)
    if linked is not None:
        return linked, SignInOutcome.LINKED
    created = await repo.users.create(session, claims)
    return None if created is None else (created, SignInOutcome.CREATED)


def _signed_in(row: UserRow, outcome: SignInOutcome) -> SignedIn:
    return SignedIn(user=User.model_validate(row), outcome=outcome)


async def _try_sign_in(
    session: AsyncSession, profile: ProviderProfile, claims: UserClaims, now: datetime
) -> SignedIn | None:
    identity = await repo.identities.get(session, profile.provider, profile.subject)
    if identity is not None:
        await repo.identities.record_login(
            session, identity.id, email=claims.email, email_verified=profile.email_verified, now=now
        )
        row = await repo.users.get(session, identity.user_id)
        return None if row is None else _signed_in(row, SignInOutcome.EXISTING)
    found = await _user_for(session, claims)
    if found is None:
        return None
    row, outcome = found
    inserted = await repo.identities.create(
        session,
        user_id=row.id,
        provider=profile.provider,
        subject=profile.subject,
        email=claims.email,
        email_verified=profile.email_verified,
        now=now,
    )
    return None if inserted is None else _signed_in(row, outcome)
