"""Suggestion routes: an idea's suggestions and the status of one.

Suggestions are written through the module's service (the Advisor's path) and read and updated
over HTTP.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.core.errors import RunNotFoundError
from metis.helpers.ids import uuid7
from metis.modules import scoring
from metis.modules.scoring import NewSuggestion, ScoreTrigger
from tests.modules.ideas.idea_helpers import IDEAS_URL, Caller, create, member_of, owner
from tests.modules.scoring.scoring_helpers import Sessions, in_workspace, marks

SUGGESTIONS_URL = "/v1/suggestions"
SOURCE = {"url": "https://example.com/report", "title": "Report", "quote": "A quote."}


def _new(title: str = "Niche down", **fields: Any) -> NewSuggestion:
    data: dict[str, Any] = {
        "kind": "niche",
        "title": title,
        "rationale": "Agencies are underserved.",
        "target_params": ["uniqueness", "market_demand"],
        "expected_impact": "uniqueness up by 2",
        "evidence": [SOURCE],
        **fields,
    }
    return NewSuggestion.model_validate(data)


async def _score(engine: AsyncEngine, sessions: Sessions, caller: Caller, idea_id: str) -> UUID:
    workspace_id, idea, run_id = UUID(caller.workspace_id), UUID(idea_id), uuid7()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ideas.workflow_runs (id, workspace_id, idea_id, status) "
                "VALUES (:id, :ws, :idea, 'succeeded')"
            ),
            {"id": run_id, "ws": workspace_id, "idea": idea},
        )
    async with in_workspace(sessions, workspace_id) as session:
        score = await scoring.record_score(
            session, workspace_id, idea, run_id, marks(4), ScoreTrigger.MANUAL
        )
    return score.id


async def _save(
    sessions: Sessions, caller: Caller, idea_id: str, score_run_id: UUID, data: NewSuggestion
) -> UUID:
    workspace_id = UUID(caller.workspace_id)
    async with in_workspace(sessions, workspace_id) as session:
        saved = await scoring.save_suggestion(
            session, workspace_id, UUID(idea_id), score_run_id, data
        )
    return saved.id


async def test_an_idea_lists_its_suggestions_for_any_member_newest_score_run_first(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    bob = await member_of(client, engine, ada)
    idea = await create(client, ada)
    first = await _score(engine, app_sessions, ada, idea["id"])
    second = await _score(engine, app_sessions, ada, idea["id"])
    await _save(app_sessions, ada, idea["id"], first, _new("Old"))
    await _save(app_sessions, ada, idea["id"], second, _new("New one"))
    await _save(app_sessions, ada, idea["id"], second, _new("New two", kind="pricing"))

    response = await client.get(f"{IDEAS_URL}/{idea['id']}/suggestions", headers=bob.headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [i["title"] for i in items] == ["New one", "New two", "Old"]
    top = items[0]
    assert (top["kind"], top["status"], top["score_run_id"]) == ("niche", "open", str(second))
    assert top["target_params"] == ["uniqueness", "market_demand"]
    assert top["evidence"] == [SOURCE]
    assert "workspace_id" not in top


async def test_the_list_can_be_narrowed_to_one_score_run(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    first = await _score(engine, app_sessions, ada, idea["id"])
    second = await _score(engine, app_sessions, ada, idea["id"])
    await _save(app_sessions, ada, idea["id"], first, _new("Old"))
    await _save(app_sessions, ada, idea["id"], second, _new("New"))

    response = await client.get(
        f"{IDEAS_URL}/{idea['id']}/suggestions",
        params={"score_run_id": str(first)},
        headers=ada.headers,
    )

    assert [i["title"] for i in response.json()["items"]] == ["Old"]


async def test_an_idea_without_suggestions_has_an_empty_list(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)

    response = await client.get(f"{IDEAS_URL}/{idea['id']}/suggestions", headers=ada.headers)

    assert (response.status_code, response.json()) == (200, {"items": []})


@pytest.mark.parametrize("who", ["unknown", "other_workspace"])
async def test_an_unknown_or_foreign_idea_is_not_found(
    client: httpx.AsyncClient, engine: AsyncEngine, who: str
) -> None:
    ada = await owner(client, engine, "ada")
    grace = await owner(client, engine, "grace")
    idea = await create(client, ada)
    idea_id = str(uuid4()) if who == "unknown" else idea["id"]

    response = await client.get(f"{IDEAS_URL}/{idea_id}/suggestions", headers=grace.headers)

    assert response.status_code == 404
    assert response.json()["code"] == "idea.not_found"


async def test_a_member_can_mark_a_suggestion_accepted_dismissed_and_open_again(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    bob = await member_of(client, engine, ada)
    idea = await create(client, ada)
    score_run_id = await _score(engine, app_sessions, ada, idea["id"])
    suggestion_id = await _save(app_sessions, ada, idea["id"], score_run_id, _new())

    seen = []
    for caller, status in ((bob, "accepted"), (ada, "dismissed"), (bob, "open")):
        response = await client.patch(
            f"{SUGGESTIONS_URL}/{suggestion_id}", json={"status": status}, headers=caller.headers
        )
        assert response.status_code == 200, response.text
        seen.append(response.json()["status"])

    assert seen == ["accepted", "dismissed", "open"]
    assert response.json()["title"] == "Niche down"  # the text did not change


@pytest.mark.parametrize("body", [{"status": "done"}, {}])
async def test_a_bad_status_body_is_422(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions, body: dict[str, Any]
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    score_run_id = await _score(engine, app_sessions, ada, idea["id"])
    suggestion_id = await _save(app_sessions, ada, idea["id"], score_run_id, _new())

    response = await client.patch(
        f"{SUGGESTIONS_URL}/{suggestion_id}", json=body, headers=ada.headers
    )

    assert response.status_code == 422


async def test_an_unknown_or_foreign_suggestion_is_not_found(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine, "ada")
    grace = await owner(client, engine, "grace")
    idea = await create(client, ada)
    score_run_id = await _score(engine, app_sessions, ada, idea["id"])
    suggestion_id = await _save(app_sessions, ada, idea["id"], score_run_id, _new())

    for url in (f"{SUGGESTIONS_URL}/{uuid4()}", f"{SUGGESTIONS_URL}/{suggestion_id}"):
        response = await client.patch(url, json={"status": "accepted"}, headers=grace.headers)
        assert response.status_code == 404
        assert response.json()["code"] == "score.suggestion_not_found"


async def test_a_suggestion_of_an_archived_idea_is_not_found(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    score_run_id = await _score(engine, app_sessions, ada, idea["id"])
    suggestion_id = await _save(app_sessions, ada, idea["id"], score_run_id, _new())
    await client.delete(f"{IDEAS_URL}/{idea['id']}", headers=ada.headers)

    response = await client.patch(
        f"{SUGGESTIONS_URL}/{suggestion_id}", json={"status": "accepted"}, headers=ada.headers
    )

    assert response.status_code == 404


async def test_the_service_refuses_a_score_run_of_another_idea(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    one = await create(client, ada)
    two = await create(client, ada, title="Another idea")
    score_of_one = await _score(engine, app_sessions, ada, one["id"])

    with pytest.raises(RunNotFoundError):
        await _save(app_sessions, ada, two["id"], score_of_one, _new())


@pytest.mark.parametrize(
    "fields",
    [
        {"evidence": []},
        {"target_params": []},
        {"target_params": ["uniqueness", "uniqueness"]},
        {"target_params": ["uniqueness", "value", "timing", "feasibility"]},
        {"kind": "rewrite"},
        {"title": " "},
    ],
)
def test_a_suggestion_needs_a_source_and_one_to_three_distinct_parameters(
    fields: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 - pydantic's ValidationError is a ValueError
        _new(**fields)
