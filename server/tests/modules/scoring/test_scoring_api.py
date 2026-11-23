"""Score routes: history, latest and one score run by id.

Scores are written through the module's service (the Scorer's path) and read over HTTP.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.helpers.ids import uuid7
from metis.modules import scoring
from metis.modules.scoring import NewParamScore, ScoreParam, ScoreTrigger
from tests.modules.ideas.idea_helpers import IDEAS_URL, Caller, create, member_of, owner
from tests.modules.scoring.scoring_helpers import Sessions, in_workspace, marks, param


async def _score(
    engine: AsyncEngine,
    sessions: Sessions,
    caller: Caller,
    idea_id: str,
    params: list[NewParamScore] | None = None,
) -> UUID:
    """Record a score of the idea through a finished run (an idea has one active run)."""
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
            session,
            workspace_id,
            idea,
            run_id,
            marks(7) if params is None else params,
            ScoreTrigger.MANUAL,
        )
    return score.id


async def _get(client: httpx.AsyncClient, caller: Caller, url: str) -> httpx.Response:
    return await client.get(url, headers=caller.headers)


def _code(response: httpx.Response) -> Any:
    return response.json()["code"]


async def test_the_latest_score_is_readable_by_any_member_with_all_six_params(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    bob = await member_of(client, engine, ada)
    idea = await create(client, ada)
    score_id = await _score(engine, app_sessions, ada, idea["id"])

    response = await _get(client, bob, f"{IDEAS_URL}/{idea['id']}/scores/latest")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["id"], body["idea_id"], body["rubric_version"]) == (str(score_id), idea["id"], 1)
    assert (body["trigger"], body["total"], body["band"]) == ("manual", 70, "promising")
    assert body["weights"] == {
        "problem_severity": 25,
        "uniqueness": 25,
        "market_demand": 15,
        "value": 15,
        "feasibility": 10,
        "timing": 10,
    }
    assert [p["param"] for p in body["params"]] == [p.value for p in ScoreParam]
    severity = body["params"][0]
    assert (severity["weight"], severity["raw"], severity["weighted"]) == (25, 7, 17.5)
    assert severity["confidence"] == 0.7
    assert severity["no_evidence"] is False
    assert severity["evidence"] == [
        {"url": "https://example.com/report", "title": "Report", "quote": "A quote."}
    ]
    assert "workspace_id" not in body


async def test_the_current_score_of_the_idea_follows_the_latest_score(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    await _score(engine, app_sessions, ada, idea["id"])

    response = await _get(client, ada, f"{IDEAS_URL}/{idea['id']}")

    assert response.json()["current_score"] == 70


async def test_the_history_is_newest_first_without_params(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    first = await _score(engine, app_sessions, ada, idea["id"], marks(2))
    second = await _score(engine, app_sessions, ada, idea["id"], marks(9))

    response = await _get(client, ada, f"{IDEAS_URL}/{idea['id']}/scores")

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [(i["id"], i["total"], i["band"]) for i in items] == [
        (str(second), 90, "build"),
        (str(first), 20, "advise"),
    ]
    assert all("params" not in i and "workspace_id" not in i for i in items)


async def test_an_unscored_idea_has_an_empty_history_and_no_latest(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)

    history = await _get(client, ada, f"{IDEAS_URL}/{idea['id']}/scores")
    latest = await _get(client, ada, f"{IDEAS_URL}/{idea['id']}/scores/latest")

    assert (history.status_code, history.json()) == (200, {"items": []})
    assert latest.status_code == 404
    assert _code(latest) == "score.not_found"


async def test_scores_of_unknown_archived_or_foreign_ideas_are_idea_not_found(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    grace = await owner(client, engine, "grace")
    idea = await create(client, ada)
    await _score(engine, app_sessions, ada, idea["id"])

    urls = [
        (grace, f"{IDEAS_URL}/{idea['id']}/scores"),
        (grace, f"{IDEAS_URL}/{idea['id']}/scores/latest"),
        (ada, f"{IDEAS_URL}/{uuid7()}/scores"),
        (ada, f"{IDEAS_URL}/{uuid7()}/scores/latest"),
    ]
    await client.delete(f"{IDEAS_URL}/{idea['id']}", headers=ada.headers)
    urls += [
        (ada, f"{IDEAS_URL}/{idea['id']}/scores"),
        (ada, f"{IDEAS_URL}/{idea['id']}/scores/latest"),
    ]

    for caller, url in urls:
        response = await _get(client, caller, url)
        assert response.status_code == 404, url
        assert _code(response) == "idea.not_found"


async def test_a_score_run_is_readable_by_id(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    no_evidence = [
        *marks(6)[:5],
        param(ScoreParam.TIMING, raw=2, evidence=[], no_evidence=True, confidence=0.2),
    ]
    score_id = await _score(engine, app_sessions, ada, idea["id"], no_evidence)

    response = await _get(client, ada, f"/v1/scores/{score_id}")

    assert response.status_code == 200, response.text
    timing = response.json()["params"][-1]
    assert (timing["no_evidence"], timing["evidence"], timing["confidence"]) == (True, [], 0.2)


async def test_unknown_foreign_or_archived_score_runs_are_not_found(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    grace = await owner(client, engine, "grace")
    idea = await create(client, ada)
    score_id = await _score(engine, app_sessions, ada, idea["id"])
    await client.delete(f"{IDEAS_URL}/{idea['id']}", headers=ada.headers)

    for caller, target in ((grace, score_id), (ada, uuid7()), (ada, score_id)):
        response = await _get(client, caller, f"/v1/scores/{target}")
        assert response.status_code == 404
        assert _code(response) == "score.run_not_found"


# ------------------------------------------------------------------ summaries


SUMMARIES_URL = "/v1/scores/summaries"


async def test_summaries_give_totals_oldest_first_and_the_latest_band(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    await _score(engine, app_sessions, ada, idea["id"], marks(5))
    await _score(engine, app_sessions, ada, idea["id"], marks(9))

    response = await _get(client, ada, f"{SUMMARIES_URL}?idea_ids={idea['id']}")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "items": [{"idea_id": idea["id"], "band": "build", "totals": [50, 90]}]
    }


async def test_summaries_match_the_score_history_of_each_idea(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    first = await create(client, ada, title="First idea")
    second = await create(client, ada, title="Second idea")
    for raw in (3, 6, 8):
        await _score(engine, app_sessions, ada, first["id"], marks(raw))
    await _score(engine, app_sessions, ada, second["id"], marks(4))

    response = await _get(
        client, ada, f"{SUMMARIES_URL}?idea_ids={first['id']},{second['id']},{first['id']}"
    )

    by_idea = {item["idea_id"]: item for item in response.json()["items"]}
    for idea in (first, second):
        history = (await _get(client, ada, f"{IDEAS_URL}/{idea['id']}/scores")).json()["items"]
        assert by_idea[idea["id"]]["totals"] == [i["total"] for i in reversed(history)]
        assert by_idea[idea["id"]]["band"] == history[0]["band"]
    assert len(by_idea) == 2


async def test_summaries_leave_out_unscored_unknown_foreign_and_archived_ideas(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    grace = await owner(client, engine, "grace")
    scored = await create(client, ada, title="Scored idea")
    unscored = await create(client, ada, title="Unscored idea")
    archived = await create(client, ada, title="Archived idea")
    foreign = await create(client, grace, title="Foreign idea")
    for idea, caller in ((scored, ada), (archived, ada), (foreign, grace)):
        await _score(engine, app_sessions, caller, idea["id"])
    await client.delete(f"{IDEAS_URL}/{archived['id']}", headers=ada.headers)
    ids = ",".join([scored["id"], unscored["id"], archived["id"], foreign["id"], str(uuid7())])

    response = await _get(client, ada, f"{SUMMARIES_URL}?idea_ids={ids}")

    assert [i["idea_id"] for i in response.json()["items"]] == [scored["id"]]


async def test_a_score_moves_the_idea_to_the_top_of_the_list_without_a_new_version(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    older = await create(client, ada, title="Older idea")
    await create(client, ada, title="Newer idea")

    await _score(engine, app_sessions, ada, older["id"])

    first = (await _get(client, ada, IDEAS_URL)).json()["items"][0]
    assert first["id"] == older["id"]
    assert first["version"] == older["version"]


@pytest.mark.parametrize(
    "query",
    [
        "",
        "idea_ids=",
        "idea_ids=nope",
        f"idea_ids={uuid7()},nope",
        "idea_ids=" + ",".join(str(uuid7()) for _ in range(51)),
    ],
)
async def test_summaries_reject_missing_malformed_or_too_many_ids(
    client: httpx.AsyncClient, engine: AsyncEngine, query: str
) -> None:
    ada = await owner(client, engine)

    response = await _get(client, ada, f"{SUMMARIES_URL}?{query}")

    assert response.status_code == 422, response.text


async def test_summaries_need_a_session(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{SUMMARIES_URL}?idea_ids={uuid7()}")

    assert response.status_code == 401, response.text
