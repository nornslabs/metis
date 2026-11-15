"""Auth's public user lookups: ``get_user`` and ``find_user_by_email``.

Seam: the functions exported by ``metis.modules.auth``, called with a real
``AsyncSession`` on a Postgres migrated to head. Users are made by auth's own
sign-in (``tests.helpers.auth.create_user``).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from metis.modules import auth
from tests.helpers.auth import create_user


async def test_get_user_returns_the_user(engine: AsyncEngine) -> None:
    user_id = await create_user(engine, "google-ada", "ada@example.com", "Ada")

    async with AsyncSession(engine) as session:
        user = await auth.get_user(session, user_id)

    assert user is not None
    assert (user.id, user.email, user.name) == (user_id, "ada@example.com", "Ada")


async def test_get_user_returns_none_for_an_unknown_id(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        assert await auth.get_user(session, uuid4()) is None


@pytest.mark.parametrize("email", ["ada@example.com", "  ADA@Example.com ", "Ada@example.COM"])
async def test_find_user_by_email_ignores_case_and_surrounding_spaces(
    engine: AsyncEngine, email: str
) -> None:
    user_id = await create_user(engine, "google-ada", "ada@example.com")

    async with AsyncSession(engine) as session:
        user = await auth.find_user_by_email(session, email)

    assert user is not None
    assert user.id == user_id


async def test_find_user_by_email_returns_none_when_nobody_has_it(engine: AsyncEngine) -> None:
    await create_user(engine, "google-ada", "ada@example.com")

    async with AsyncSession(engine) as session:
        assert await auth.find_user_by_email(session, "bob@example.com") is None
