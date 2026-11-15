"""Identity services: users, workspaces and membership.

Seam: the public functions of ``metis.modules.identity`` called with a real
``AsyncSession`` on a Postgres migrated to head. Every session runs as a
``NOLOGIN NOSUPERUSER NOBYPASSRLS`` role, because superusers bypass RLS.
Tests assert only returned DTOs, raised errors and what the services read back.

Set ``TEST_DATABASE_URL`` to a database migrated with ``alembic upgrade head``.
Tests skip only when Postgres is unreachable or the identity tables are missing.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from metis.core.errors import (
    AlreadyMemberError,
    InvalidInputError,
    MemberUserNotFoundError,
    OAuthFailedError,
    PermissionDeniedError,
)
from metis.modules import identity
from metis.modules.auth import User
from metis.modules.auth import service as auth_service
from metis.modules.identity import MemberRole
from tests.helpers.auth import TRUNCATE_USERS, google_profile

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/metis"
)
TEST_ROLE = "metis_identity_test"

_CREATE_TEST_ROLE = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{TEST_ROLE}') THEN
        CREATE ROLE {TEST_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END
$$
"""
_GRANTS = [
    f"GRANT USAGE ON SCHEMA identity TO {TEST_ROLE}",
    f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA identity TO {TEST_ROLE}",
    f"GRANT USAGE ON SCHEMA auth TO {TEST_ROLE}",
    f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA auth TO {TEST_ROLE}",
]
_MIGRATED = (
    "SELECT to_regclass('identity.members') IS NOT NULL AND to_regclass('auth.users') IS NOT NULL"
)
_TRUNCATE = TRUNCATE_USERS


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """A migrated database with empty identity tables and the test role."""
    engine = create_async_engine(DATABASE_URL)
    try:
        async with engine.connect() as conn:
            migrated = await conn.scalar(text(_MIGRATED))
    except Exception:  # noqa: BLE001
        await engine.dispose()
        pytest.skip("Postgres not reachable")
    if not migrated:
        await engine.dispose()
        pytest.skip("auth/identity tables missing; run `alembic upgrade head`")

    async with engine.begin() as conn:
        await conn.execute(text(_CREATE_TEST_ROLE))
        for grant in _GRANTS:
            await conn.execute(text(grant))
        await conn.execute(text(_TRUNCATE))
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text(_TRUNCATE))
    await engine.dispose()


@asynccontextmanager
async def app_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """One committed transaction as the non-superuser role, like the app will use."""
    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        await session.execute(text(f"SET LOCAL ROLE {TEST_ROLE}"))
        yield session


async def sign_in(
    engine: AsyncEngine, sub: str, email: str, name: str | None = None, image: str | None = None
) -> User:
    """A verified Google sign-in, then the user's personal workspace.

    Auth's sign-in finds or creates the user; the personal workspace is made
    the way the app's first workspace-scoped call makes it.
    """
    async with app_session(engine) as session:
        signed_in = await auth_service.sign_in(session, google_profile(sub, email, name, image))
        await identity.ensure_personal_workspace(session, signed_in.user)
        return signed_in.user


async def workspaces_of(engine: AsyncEngine, user: User) -> list[identity.Membership]:
    async with app_session(engine) as session:
        return await identity.list_workspaces(session, user)


async def test_first_sign_in_creates_user_and_owned_personal_workspace(
    engine: AsyncEngine,
) -> None:
    user = await sign_in(engine, "google-ada", "ada@example.com", "Ada")

    assert user.email == "ada@example.com"
    assert user.name == "Ada"
    memberships = await workspaces_of(engine, user)
    assert len(memberships) == 1
    assert memberships[0].role is MemberRole.OWNER
    assert memberships[0].workspace.is_personal is True
    assert memberships[0].workspace.name == "Personal"
    assert memberships[0].workspace.created_by == user.id


async def test_second_sign_in_creates_nothing_new(engine: AsyncEngine) -> None:
    first = await sign_in(engine, "google-ada", "ada@example.com", "Ada")

    second = await sign_in(engine, "google-ada", "ada@example.com", "Ada")

    assert second.id == first.id
    memberships = await workspaces_of(engine, second)
    assert [m.workspace.is_personal for m in memberships] == [True]


async def test_concurrent_first_sign_ins_create_one_user_and_one_workspace(
    engine: AsyncEngine,
) -> None:
    first, second = await asyncio.gather(
        sign_in(engine, "google-ada", "ada@example.com"),
        sign_in(engine, "google-ada", "ada@example.com"),
    )

    assert first.id == second.id
    assert len(await workspaces_of(engine, first)) == 1


async def test_email_is_matched_case_insensitively(engine: AsyncEngine) -> None:
    user = await sign_in(engine, "google-ada", "  Ada@Example.COM ")

    assert user.email == "ada@example.com"


@pytest.mark.parametrize("email", ["not-an-email", "ada@", "a da@example.com"])
async def test_invalid_profile_email_fails_the_sign_in(engine: AsyncEngine, email: str) -> None:
    with pytest.raises(OAuthFailedError):
        await sign_in(engine, "google-ada", email)


async def create_workspace(engine: AsyncEngine, user: User, name: str) -> identity.Workspace:
    async with app_session(engine) as session:
        return await identity.create_workspace(session, user, name)


async def test_created_workspace_is_owned_by_its_creator(engine: AsyncEngine) -> None:
    ada = await sign_in(engine, "google-ada", "ada@example.com")

    team = await create_workspace(engine, ada, "  Analytical Engines  ")

    assert team.name == "Analytical Engines"
    assert team.is_personal is False
    memberships = await workspaces_of(engine, ada)
    assert [(m.workspace.name, m.role) for m in memberships] == [
        ("Personal", MemberRole.OWNER),
        ("Analytical Engines", MemberRole.OWNER),
    ]


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
async def test_workspace_name_must_be_non_blank_and_short(engine: AsyncEngine, name: str) -> None:
    ada = await sign_in(engine, "google-ada", "ada@example.com")

    with pytest.raises(InvalidInputError):
        await create_workspace(engine, ada, name)


async def add_member(
    engine: AsyncEngine, actor: User, workspace: identity.Workspace, email: str, role: MemberRole
) -> identity.Membership:
    async with app_session(engine) as session:
        return await identity.add_member(session, actor, workspace.id, email, role)


async def test_owner_adds_an_existing_user_as_member(engine: AsyncEngine) -> None:
    ada = await sign_in(engine, "google-ada", "ada@example.com")
    bob = await sign_in(engine, "google-bob", "bob@example.com")
    team = await create_workspace(engine, ada, "Engines")

    added = await add_member(engine, ada, team, "BOB@example.com", MemberRole.MEMBER)

    assert added.workspace.id == team.id
    assert added.role is MemberRole.MEMBER
    bob_sees = [(m.workspace.name, m.role) for m in await workspaces_of(engine, bob)]
    assert bob_sees == [("Personal", MemberRole.OWNER), ("Engines", MemberRole.MEMBER)]


async def test_member_who_is_not_owner_cannot_add_members(engine: AsyncEngine) -> None:
    ada = await sign_in(engine, "google-ada", "ada@example.com")
    bob = await sign_in(engine, "google-bob", "bob@example.com")
    await sign_in(engine, "google-cy", "cy@example.com")
    team = await create_workspace(engine, ada, "Engines")
    await add_member(engine, ada, team, "bob@example.com", MemberRole.MEMBER)

    with pytest.raises(PermissionDeniedError):
        await add_member(engine, bob, team, "cy@example.com", MemberRole.MEMBER)


async def test_non_member_cannot_add_members(engine: AsyncEngine) -> None:
    ada = await sign_in(engine, "google-ada", "ada@example.com")
    mallory = await sign_in(engine, "google-mallory", "mallory@example.com")
    team = await create_workspace(engine, ada, "Engines")

    with pytest.raises(PermissionDeniedError):
        await add_member(engine, mallory, team, "mallory@example.com", MemberRole.OWNER)


async def test_adding_an_unknown_email_is_not_found(engine: AsyncEngine) -> None:
    ada = await sign_in(engine, "google-ada", "ada@example.com")
    team = await create_workspace(engine, ada, "Engines")

    with pytest.raises(MemberUserNotFoundError):
        await add_member(engine, ada, team, "nobody@example.com", MemberRole.MEMBER)


async def test_adding_an_existing_member_conflicts_and_keeps_their_role(
    engine: AsyncEngine,
) -> None:
    ada = await sign_in(engine, "google-ada", "ada@example.com")
    bob = await sign_in(engine, "google-bob", "bob@example.com")
    team = await create_workspace(engine, ada, "Engines")
    await add_member(engine, ada, team, "bob@example.com", MemberRole.MEMBER)

    with pytest.raises(AlreadyMemberError):
        await add_member(engine, ada, team, "bob@example.com", MemberRole.OWNER)

    roles = {m.workspace.id: m.role for m in await workspaces_of(engine, bob)}
    assert roles[team.id] is MemberRole.MEMBER


async def test_member_of_a_cannot_list_workspace_b(engine: AsyncEngine) -> None:
    """Service-level view; the RLS-only proof is the raw ``members`` read below."""
    ada = await sign_in(engine, "google-ada", "ada@example.com")
    bob = await sign_in(engine, "google-bob", "bob@example.com")
    ada_team = await create_workspace(engine, ada, "Engines")

    bob_sees = {m.workspace.id for m in await workspaces_of(engine, bob)}

    assert ada_team.id not in bob_sees
    assert all(m.workspace.created_by == bob.id for m in await workspaces_of(engine, bob))


async def _visible_member_user_ids(
    engine: AsyncEngine, setting: str | None = None, value: object = None
) -> set[str]:
    """Raw read of ``identity.members`` as the app role: what RLS alone lets through."""
    async with app_session(engine) as session:
        if setting is not None:
            await session.execute(
                text("SELECT set_config(:name, :value, true)"),
                {"name": setting, "value": str(value)},
            )
        rows = await session.execute(text("SELECT user_id FROM identity.members"))
        return {str(user_id) for (user_id,) in rows}


async def test_members_rls_scopes_rows_by_context_and_fails_closed(
    engine: AsyncEngine,
) -> None:
    ada = await sign_in(engine, "google-ada", "ada@example.com")
    bob = await sign_in(engine, "google-bob", "bob@example.com")
    bob_personal = (await workspaces_of(engine, bob))[0].workspace

    assert await _visible_member_user_ids(engine) == set()
    assert await _visible_member_user_ids(engine, "app.user_id", ada.id) == {str(ada.id)}
    assert await _visible_member_user_ids(engine, "app.workspace_id", bob_personal.id) == {
        str(bob.id)
    }


async def test_nothing_persists_when_the_caller_rolls_back(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session, session.begin():
        await session.execute(text(f"SET LOCAL ROLE {TEST_ROLE}"))
        await auth_service.sign_in(session, google_profile("google-ghost", "ghost@example.com"))
        await session.rollback()

    ada = await sign_in(engine, "google-ada", "ada@example.com")
    with pytest.raises(MemberUserNotFoundError):
        await add_member(
            engine,
            ada,
            (await workspaces_of(engine, ada))[0].workspace,
            "ghost@example.com",
            MemberRole.MEMBER,
        )


@pytest.mark.parametrize("role", ["admin", ""])
async def test_adding_with_an_unknown_role_is_rejected(engine: AsyncEngine, role: str) -> None:
    ada = await sign_in(engine, "google-ada", "ada@example.com")
    await sign_in(engine, "google-bob", "bob@example.com")
    team = await create_workspace(engine, ada, "Engines")

    with pytest.raises(InvalidInputError):
        await add_member(engine, ada, team, "bob@example.com", role)  # type: ignore[arg-type]


async def test_adding_with_an_invalid_email_is_rejected(engine: AsyncEngine) -> None:
    ada = await sign_in(engine, "google-ada", "ada@example.com")
    team = await create_workspace(engine, ada, "Engines")

    with pytest.raises(InvalidInputError):
        await add_member(engine, ada, team, "bob", MemberRole.MEMBER)


async def test_image_must_be_an_http_url(engine: AsyncEngine) -> None:
    with pytest.raises(OAuthFailedError):
        await sign_in(engine, "google-ada", "ada@example.com", image="javascript:alert(1)")


async def test_same_email_from_another_subject_links_to_the_existing_account(
    engine: AsyncEngine,
) -> None:
    ada = await sign_in(engine, "google-ada", "ada@example.com")

    linked = await sign_in(engine, "google-other", "ada@example.com")

    assert linked.id == ada.id


async def test_services_leave_the_callers_workspace_context_unchanged(
    engine: AsyncEngine,
) -> None:
    ada = await sign_in(engine, "google-ada", "ada@example.com")
    await sign_in(engine, "google-bob", "bob@example.com")
    caller_ws = (await workspaces_of(engine, ada))[0].workspace
    current = text("SELECT current_setting('app.workspace_id', true)")

    async with app_session(engine) as session:
        await session.execute(
            text("SELECT set_config('app.workspace_id', :v, true)"), {"v": str(caller_ws.id)}
        )
        team = await identity.create_workspace(session, ada, "Engines")
        await identity.add_member(session, ada, team.id, "bob@example.com", MemberRole.MEMBER)
        await identity.list_workspaces(session, ada)

        assert await session.scalar(current) == str(caller_ws.id)
        assert await session.scalar(text("SELECT current_setting('app.user_id', true)")) in (
            None,
            "",
        )


async def test_overlong_name_is_rejected(engine: AsyncEngine) -> None:
    with pytest.raises(OAuthFailedError):
        await sign_in(engine, "google-ada", "ada@example.com", "x" * 201)
