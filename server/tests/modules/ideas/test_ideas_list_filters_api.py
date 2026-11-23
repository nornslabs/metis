"""``GET /v1/ideas`` search, filters and last-activity order at the HTTP seam."""

from __future__ import annotations

import httpx
import pytest
from idea_helpers import IDEAS_URL, Caller, create, owner
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def _ids(client: httpx.AsyncClient, caller: Caller, query: str = "") -> list[str]:
    response = await client.get(f"{IDEAS_URL}?{query}", headers=caller.headers)
    assert response.status_code == 200, response.text
    return [idea["id"] for idea in response.json()["items"]]


async def _set(engine: AsyncEngine, idea_id: str, **columns: object) -> None:
    assignments = ", ".join(f"{name} = :{name}" for name in columns)
    async with engine.begin() as conn:
        await conn.execute(
            text(f"UPDATE ideas.ideas SET {assignments} WHERE id = :id"),  # noqa: S608
            {"id": idea_id, **columns},
        )


async def test_search_matches_titles_case_insensitively(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    crm = await create(client, ada, title="Pocket CRM")
    await create(client, ada, title="Garden planner")

    assert await _ids(client, ada, "q=pocket") == [crm["id"]]
    assert await _ids(client, ada, "q=CRM") == [crm["id"]]


async def test_search_treats_percent_and_underscore_as_plain_characters(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    literal = await create(client, ada, title="50% off planner")
    await create(client, ada, title="Garden planner")
    await create(client, ada, title="Fifty off planner")

    assert await _ids(client, ada, "q=50%25") == [literal["id"]]
    assert await _ids(client, ada, "q=_") == []


async def test_a_blank_search_lists_everything(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    await create(client, ada, title="Pocket CRM")
    await create(client, ada, title="Garden planner")

    assert len(await _ids(client, ada, "q=%20%20")) == 2


async def test_in_progress_lists_stages_before_the_spec_is_confirmed(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    early = await create(client, ada, title="Early idea")
    drafting = await create(client, ada, title="Drafting idea")
    done = await create(client, ada, title="Confirmed idea")
    await _set(engine, drafting["id"], stage="spec_draft")
    await _set(engine, done["id"], stage="spec_confirmed")

    assert set(await _ids(client, ada, "filter=in_progress")) == {early["id"], drafting["id"]}
    assert len(await _ids(client, ada, "filter=all")) == 3


async def test_scored_lists_ideas_with_a_current_score_and_combines_with_search(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    scored = await create(client, ada, title="Pocket CRM")
    other = await create(client, ada, title="Pocket garden")
    await create(client, ada, title="Pocket unscored")
    await _set(engine, scored["id"], current_score=70)
    await _set(engine, other["id"], current_score=40)

    assert set(await _ids(client, ada, "filter=scored")) == {scored["id"], other["id"]}
    assert await _ids(client, ada, "filter=scored&q=crm") == [scored["id"]]
    assert await _ids(client, ada, "filter=scored&q=unscored") == []


async def test_filters_hold_across_cursor_pages(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    matching = [await create(client, ada, title=f"Match {n}") for n in range(3)]
    await create(client, ada, title="Other")

    first = (await client.get(f"{IDEAS_URL}?q=match&limit=2", headers=ada.headers)).json()
    second = (
        await client.get(
            f"{IDEAS_URL}?q=match&limit=2&cursor={first['next_cursor']}", headers=ada.headers
        )
    ).json()

    got = [i["id"] for i in first["items"]] + [i["id"] for i in second["items"]]
    assert got == [m["id"] for m in reversed(matching)]
    assert second["next_cursor"] is None


async def test_no_match_is_an_empty_page(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ada = await owner(client, engine)
    await create(client, ada)

    response = await client.get(f"{IDEAS_URL}?q=zzz", headers=ada.headers)

    assert response.json() == {"items": [], "next_cursor": None}


async def test_search_never_reaches_ideas_of_another_workspace(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    grace = await owner(client, engine, "grace")
    await create(client, grace, title="Pocket CRM")

    assert await _ids(client, ada, "q=pocket") == []


@pytest.mark.parametrize("query", ["filter=nope", f"q={'x' * 101}"])
async def test_a_bad_filter_or_long_search_is_422(
    client: httpx.AsyncClient, engine: AsyncEngine, query: str
) -> None:
    ada = await owner(client, engine)

    response = await client.get(f"{IDEAS_URL}?{query}", headers=ada.headers)

    assert response.status_code == 422, response.text


async def test_an_edited_idea_rises_to_the_top_by_last_activity(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    older = await create(client, ada, title="Older idea")
    newer = await create(client, ada, title="Newer idea")
    assert await _ids(client, ada) == [newer["id"], older["id"]]

    await client.patch(
        f"{IDEAS_URL}/{older['id']}",
        json={"version": older["version"], "title": "Older idea, edited"},
        headers=ada.headers,
    )

    assert await _ids(client, ada) == [older["id"], newer["id"]]


async def test_paging_returns_each_idea_once_when_one_is_edited_mid_scroll(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    created = [await create(client, ada, title=f"Idea number {n}") for n in range(4)]
    first = (await client.get(f"{IDEAS_URL}?limit=2", headers=ada.headers)).json()
    oldest = created[0]

    await client.patch(
        f"{IDEAS_URL}/{oldest['id']}",
        json={"version": oldest["version"], "title": "Oldest idea, edited"},
        headers=ada.headers,
    )
    second = (
        await client.get(f"{IDEAS_URL}?limit=2&cursor={first['next_cursor']}", headers=ada.headers)
    ).json()

    seen = [i["id"] for i in first["items"]] + [i["id"] for i in second["items"]]
    assert len(seen) == len(set(seen))
    assert second["next_cursor"] is None


async def test_a_search_over_the_limit_after_trimming_is_422_but_padding_is_not(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    padded = f"{'x' * 100}%20%20%20"

    assert (await client.get(f"{IDEAS_URL}?q={padded}", headers=ada.headers)).status_code == 200
    assert (await client.get(f"{IDEAS_URL}?q={'x' * 101}", headers=ada.headers)).status_code == 422
