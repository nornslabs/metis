"""Ideas routes (``/v1/ideas``) at the HTTP seam.

Real app, real Postgres (request session as ``metis_app``, so RLS applies) and Redis.
The outbox is read as the DB owner.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import pytest
from idea_helpers import IDEAS_URL, Caller, create, idea_body, member_of, owner
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.core.errors import ErrorCode
from tests.helpers.auth import assert_problem, auth, sign_in


async def _outbox(engine: AsyncEngine) -> list[Any]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT type, workspace_id, payload FROM core.outbox "
                "WHERE type = 'IdeaSubmitted' ORDER BY created_at, id"
            )
        )
        return list(rows.all())


# ------------------------------------------------------------------ create / read


async def test_create_returns_the_idea_at_intake(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)

    response = await client.post(
        IDEAS_URL, json={**idea_body(), "kind": "software"}, headers=ada.headers
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Pocket CRM"
    assert body["raw_text"] == "A tiny CRM for freelancers."
    assert body["kind"] == "software"
    assert body["stage"] == "intake"
    assert body["current_score"] is None
    assert body["version"] == 1
    assert body["workspace_id"] == ada.workspace_id
    assert body["created_by"] == ada.user_id
    assert "archived_at" not in body


async def test_get_returns_the_idea_and_list_contains_it(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    created = await create(client, ada)

    one = await client.get(f"{IDEAS_URL}/{created['id']}", headers=ada.headers)
    listed = await client.get(IDEAS_URL, headers=ada.headers)

    assert one.status_code == 200, one.text
    assert one.json() == created
    assert listed.json() == {"items": [created], "next_cursor": None}


async def test_get_an_unknown_idea_is_404(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ada = await owner(client, engine)

    response = await client.get(f"{IDEAS_URL}/{uuid4()}", headers=ada.headers)

    assert_problem(response, 404, ErrorCode.IDEA_NOT_FOUND)


async def test_a_malformed_idea_id_is_422(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ada = await owner(client, engine)

    response = await client.get(f"{IDEAS_URL}/not-a-uuid", headers=ada.headers)

    assert response.status_code == 422


# ------------------------------------------------------------------ validation

TITLE_OK = "x" * 120
TEXT_OK = "y" * 10_000


@pytest.mark.parametrize(
    ("body", "ok"),
    [
        ({"title": "ab", "raw_text": "long enough text"}, False),
        ({"title": "abc", "raw_text": "long enough text"}, True),
        ({"title": TITLE_OK, "raw_text": "long enough text"}, True),
        ({"title": TITLE_OK + "x", "raw_text": "long enough text"}, False),
        ({"title": "good title", "raw_text": "z" * 9}, False),
        ({"title": "good title", "raw_text": "z" * 10}, True),
        ({"title": "good title", "raw_text": TEXT_OK}, True),
        ({"title": "good title", "raw_text": TEXT_OK + "y"}, False),
        ({"title": "  ab  ", "raw_text": "long enough text"}, False),  # trimmed before counting
        ({"title": "good title", "raw_text": "   short   "}, False),
        ({"title": "good title", "raw_text": "long enough text", "kind": "hardware"}, False),
        ({"title": "good title", "raw_text": "long enough text", "stage": "scoring"}, False),
        ({"raw_text": "long enough text"}, False),
    ],
)
async def test_create_validates_title_and_text_lengths(
    client: httpx.AsyncClient, engine: AsyncEngine, body: dict[str, Any], ok: bool
) -> None:
    ada = await owner(client, engine)

    response = await client.post(IDEAS_URL, json=body, headers=ada.headers)

    assert response.status_code == (201 if ok else 422), response.text


async def test_create_trims_the_title_and_text(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)

    created = await create(client, ada, title="  Pocket CRM  ", raw_text="  A tiny CRM, padded.  ")

    assert created["title"] == "Pocket CRM"
    assert created["raw_text"] == "A tiny CRM, padded."


async def test_a_mutation_without_the_client_header_is_refused(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    headers = {k: v for k, v in ada.headers.items() if k != "X-Metis-Client"}

    response = await client.post(IDEAS_URL, json=idea_body(), headers=headers)

    assert_problem(response, 403, ErrorCode.CSRF_FAILED)


# ------------------------------------------------------------------ list / pagination


async def test_list_pages_newest_first_without_gaps_or_repeats(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    created = [await create(client, ada, title=f"Idea number {n}") for n in range(5)]
    newest_first = [idea["id"] for idea in reversed(created)]

    first = (await client.get(f"{IDEAS_URL}?limit=2", headers=ada.headers)).json()
    second = (
        await client.get(f"{IDEAS_URL}?limit=2&cursor={first['next_cursor']}", headers=ada.headers)
    ).json()
    third = (
        await client.get(f"{IDEAS_URL}?limit=2&cursor={second['next_cursor']}", headers=ada.headers)
    ).json()

    assert [i["id"] for i in first["items"]] == newest_first[0:2]
    assert [i["id"] for i in second["items"]] == newest_first[2:4]
    assert [i["id"] for i in third["items"]] == newest_first[4:5]
    assert first["next_cursor"] and second["next_cursor"]
    assert third["next_cursor"] is None


async def test_list_with_an_exact_page_has_no_next_cursor(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    for n in range(2):
        await create(client, ada, title=f"Idea number {n}")

    body = (await client.get(f"{IDEAS_URL}?limit=2", headers=ada.headers)).json()

    assert len(body["items"]) == 2
    assert body["next_cursor"] is None


async def test_an_empty_workspace_lists_nothing(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)

    response = await client.get(IDEAS_URL, headers=ada.headers)

    assert response.json() == {"items": [], "next_cursor": None}


@pytest.mark.parametrize("query", ["cursor=garbage", "cursor=", "limit=0", "limit=101", "limit=x"])
async def test_list_rejects_a_bad_cursor_or_limit(
    client: httpx.AsyncClient, engine: AsyncEngine, query: str
) -> None:
    ada = await owner(client, engine)

    response = await client.get(f"{IDEAS_URL}?{query}", headers=ada.headers)

    assert response.status_code == 422, response.text


# ------------------------------------------------------------------ edit / version


async def test_patch_edits_the_idea_and_bumps_the_version(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    created = await create(client, ada)

    response = await client.patch(
        f"{IDEAS_URL}/{created['id']}",
        json={"version": 1, "title": "Pocket CRM 2", "kind": "software"},
        headers=ada.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Pocket CRM 2"
    assert body["kind"] == "software"
    assert body["raw_text"] == created["raw_text"]
    assert body["version"] == 2
    assert body["stage"] == "intake"
    assert (await client.get(f"{IDEAS_URL}/{created['id']}", headers=ada.headers)).json() == body


async def test_patch_can_clear_the_kind(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ada = await owner(client, engine)
    created = await create(client, ada)
    url = f"{IDEAS_URL}/{created['id']}"
    await client.patch(url, json={"version": 1, "kind": "other"}, headers=ada.headers)

    response = await client.patch(url, json={"version": 2, "kind": None}, headers=ada.headers)

    assert response.json()["kind"] is None


async def test_patch_with_a_stale_version_is_a_conflict(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    created = await create(client, ada)
    url = f"{IDEAS_URL}/{created['id']}"
    await client.patch(url, json={"version": 1, "title": "First edit"}, headers=ada.headers)

    stale = await client.patch(
        url, json={"version": 1, "title": "Second edit"}, headers=ada.headers
    )

    assert_problem(stale, 409, ErrorCode.CONFLICT)
    assert (await client.get(url, headers=ada.headers)).json()["title"] == "First edit"


@pytest.mark.parametrize(
    "body",
    [
        {"version": 1},
        {"title": "No version"},
        {"version": 1, "title": "ab"},
        {"version": 1, "raw_text": "short"},
        {"version": 1, "kind": "hardware"},
        {"version": 1, "stage": "scoring"},
        {"version": 1, "title": None},
        {"version": 0, "title": "Version zero"},
    ],
)
async def test_patch_rejects_invalid_bodies(
    client: httpx.AsyncClient, engine: AsyncEngine, body: dict[str, Any]
) -> None:
    ada = await owner(client, engine)
    created = await create(client, ada)

    response = await client.patch(f"{IDEAS_URL}/{created['id']}", json=body, headers=ada.headers)

    assert response.status_code == 422, response.text


async def test_patching_an_unknown_idea_is_404(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)

    response = await client.patch(
        f"{IDEAS_URL}/{uuid4()}", json={"version": 1, "title": "Nothing here"}, headers=ada.headers
    )

    assert_problem(response, 404, ErrorCode.IDEA_NOT_FOUND)


# ------------------------------------------------------------------ archive


async def test_delete_archives_the_idea(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ada = await owner(client, engine)
    kept = await create(client, ada, title="Kept idea")
    gone = await create(client, ada, title="Archived idea")
    url = f"{IDEAS_URL}/{gone['id']}"

    deleted = await client.delete(url, headers=ada.headers)

    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""
    assert_problem(await client.get(url, headers=ada.headers), 404, ErrorCode.IDEA_NOT_FOUND)
    assert (await client.get(IDEAS_URL, headers=ada.headers)).json()["items"] == [kept]
    assert_problem(
        await client.patch(url, json={"version": 2, "title": "Edit archived"}, headers=ada.headers),
        404,
        ErrorCode.IDEA_NOT_FOUND,
    )
    assert_problem(await client.delete(url, headers=ada.headers), 404, ErrorCode.IDEA_NOT_FOUND)


async def test_archiving_keeps_the_row(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ada = await owner(client, engine)
    created = await create(client, ada)

    await client.delete(f"{IDEAS_URL}/{created['id']}", headers=ada.headers)

    async with engine.connect() as conn:
        archived_at = await conn.scalar(
            text("SELECT archived_at FROM ideas.ideas WHERE id = :id"), {"id": created["id"]}
        )
    assert archived_at is not None


async def test_archived_ideas_do_not_count_toward_pagination(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    ideas = [await create(client, ada, title=f"Idea number {n}") for n in range(3)]
    await client.delete(f"{IDEAS_URL}/{ideas[1]['id']}", headers=ada.headers)

    page = (await client.get(f"{IDEAS_URL}?limit=2", headers=ada.headers)).json()

    assert [i["id"] for i in page["items"]] == [ideas[2]["id"], ideas[0]["id"]]
    assert page["next_cursor"] is None


# ------------------------------------------------------------------ isolation


async def test_another_workspace_cannot_see_or_change_an_idea(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine, "ada")
    bob = await owner(client, engine, "bob")
    created = await create(client, ada)
    url = f"{IDEAS_URL}/{created['id']}"

    assert (await client.get(IDEAS_URL, headers=bob.headers)).json() == {
        "items": [],
        "next_cursor": None,
    }
    assert_problem(await client.get(url, headers=bob.headers), 404, ErrorCode.IDEA_NOT_FOUND)
    assert_problem(
        await client.patch(url, json={"version": 1, "title": "Hijacked"}, headers=bob.headers),
        404,
        ErrorCode.IDEA_NOT_FOUND,
    )
    assert_problem(await client.delete(url, headers=bob.headers), 404, ErrorCode.IDEA_NOT_FOUND)
    assert (await client.get(url, headers=ada.headers)).json() == created


async def test_a_user_cannot_reach_ideas_through_a_workspace_they_are_not_in(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine, "ada")
    bob = await owner(client, engine, "bob")
    await create(client, ada)

    response = await client.get(IDEAS_URL, headers=auth(bob.token, ada.workspace_id))

    assert_problem(response, 403, ErrorCode.FORBIDDEN)


async def test_the_database_hides_other_workspaces_even_without_the_query_filter(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine, "ada")
    bob = await owner(client, engine, "bob")
    await create(client, ada)
    await create(client, bob, title="Bob's idea")

    async with engine.begin() as conn:
        await conn.execute(text("SET LOCAL ROLE metis_app"))
        await conn.execute(
            text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": bob.workspace_id}
        )
        titles = (await conn.execute(text("SELECT title FROM ideas.ideas"))).scalars().all()

    assert titles == ["Bob's idea"]


# ------------------------------------------------------------------ who may change an idea


async def test_workspace_members_read_but_only_creator_or_owner_change(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine, "ada")
    ben = await member_of(client, engine, ada, "ben")
    cy = await member_of(client, engine, ada, "cy")
    by_ben = await create(client, ben, title="Ben's idea")
    url = f"{IDEAS_URL}/{by_ben['id']}"

    assert (await client.get(url, headers=cy.headers)).json() == by_ben
    assert len((await client.get(IDEAS_URL, headers=cy.headers)).json()["items"]) == 1
    assert_problem(
        await client.patch(url, json={"version": 1, "title": "Cy edit"}, headers=cy.headers),
        403,
        ErrorCode.IDEA_NOT_OWNER,
    )
    assert_problem(await client.delete(url, headers=cy.headers), 403, ErrorCode.IDEA_NOT_OWNER)
    creator_edit = await client.patch(
        url, json={"version": 1, "title": "Ben edit"}, headers=ben.headers
    )
    owner_edit = await client.patch(
        url, json={"version": 2, "title": "Ada edit"}, headers=ada.headers
    )
    assert creator_edit.status_code == 200, creator_edit.text
    assert owner_edit.status_code == 200, owner_edit.text


async def test_a_creator_and_an_owner_can_archive(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine, "ada")
    ben = await member_of(client, engine, ada, "ben")
    by_ben = await create(client, ben, title="Ben's idea")
    by_ben_2 = await create(client, ben, title="Ben's other idea")

    by_creator = await client.delete(f"{IDEAS_URL}/{by_ben['id']}", headers=ben.headers)
    by_owner = await client.delete(f"{IDEAS_URL}/{by_ben_2['id']}", headers=ada.headers)

    assert by_creator.status_code == 204
    assert by_owner.status_code == 204


# ------------------------------------------------------------------ outbox


async def test_create_writes_an_idea_submitted_event(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)

    before = await _outbox(engine)

    created = await create(client, ada)

    events = (await _outbox(engine))[len(before) :]
    assert len(events) == 1
    event_type, workspace_id, payload = events[0]
    assert event_type == "IdeaSubmitted"
    assert str(workspace_id) == ada.workspace_id
    assert payload == {"idea_id": created["id"], "created_by": ada.user_id}


async def test_a_refused_create_writes_no_event(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    before = await _outbox(engine)

    await client.post(IDEAS_URL, json={"title": "no", "raw_text": "short"}, headers=ada.headers)

    assert await _outbox(engine) == before


async def test_editing_and_archiving_write_no_event(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    created = await create(client, ada)
    url = f"{IDEAS_URL}/{created['id']}"
    before = await _outbox(engine)

    await client.patch(url, json={"version": 1, "title": "Edited title"}, headers=ada.headers)
    await client.delete(url, headers=ada.headers)

    assert await _outbox(engine) == before


async def test_ideas_need_a_signed_in_user(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    token = await sign_in(engine)

    response = await client.get(IDEAS_URL)  # no cookie
    ok = await client.get(IDEAS_URL, headers=auth(token))

    assert_problem(response, 401, ErrorCode.NOT_SIGNED_IN)
    assert ok.status_code == 200


def test_the_caller_type_exposes_headers() -> None:
    caller = Caller(token="t", user_id="u", workspace_id="w")

    assert caller.headers["X-Workspace-Id"] == "w"
