"""Spec routes (read, list, edit, confirm) at the HTTP seam, on real Postgres as ``metis_app``.

The Architect's draft is saved through the module's service (its path); everything a user does
goes over HTTP. Confirming resumes the waiting run by enqueueing the job, which is faked here.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.core import jobs
from metis.modules import ideas
from metis.modules.ideas import NewSpecHld, spec_hash
from tests.helpers.auth import assert_problem
from tests.modules.ideas.idea_helpers import IDEAS_URL, create, member_of, owner
from tests.modules.ideas.spec_helpers import (
    DRAFT,
    draft_idea,
    idea_row,
    set_stage,
    spec_confirmed_events,
    waiting_run,
)
from tests.modules.scoring.scoring_helpers import Sessions, in_workspace

EDITED = DRAFT.replace("A tiny CRM.", "A tiny CRM that nags you.")


@pytest.fixture
def queue(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Every ``enqueue`` call the confirm route makes."""
    calls: list[dict[str, Any]] = []

    async def fake_enqueue(job_name: str, *args: Any, **kwargs: Any) -> None:
        calls.append({"job": job_name, **kwargs})

    monkeypatch.setattr(jobs, "enqueue", fake_enqueue)
    return calls


def _spec(idea_id: str, tail: str = "") -> str:
    return f"{IDEAS_URL}/{idea_id}/spec{tail}"


async def _edit(
    client: httpx.AsyncClient, caller: Any, idea_id: str, base: int, content: str = EDITED
) -> httpx.Response:
    return await client.post(
        _spec(idea_id, "/versions"),
        json={"base_number": base, "content_md": content},
        headers=caller.headers,
    )


async def _confirm(
    client: httpx.AsyncClient, caller: Any, idea_id: str, number: int
) -> httpx.Response:
    return await client.post(
        _spec(idea_id, "/confirm"), json={"number": number}, headers=caller.headers
    )


# ------------------------------------------------------------------------------ read


async def test_an_idea_without_a_spec_has_neither_latest_nor_confirmed(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)

    response = await client.get(_spec(idea["id"]), headers=ada.headers)

    assert response.status_code == 200, response.text
    assert response.json() == {"latest": None, "confirmed": None, "hld": None}


async def test_any_member_reads_the_latest_version_and_the_list(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    bob = await member_of(client, engine, ada)
    idea = await draft_idea(client, engine, app_sessions, ada)
    assert (await _edit(client, ada, idea["id"], 1)).status_code == 201

    overview = await client.get(_spec(idea["id"]), headers=bob.headers)
    listed = await client.get(_spec(idea["id"], "/versions"), headers=bob.headers)

    latest = overview.json()["latest"]
    assert (latest["number"], latest["source"]) == (2, "user")
    assert latest["sections"]["solution"] == "A tiny CRM that nags you."
    assert overview.json()["confirmed"] is None
    items = listed.json()["items"]
    assert [(i["number"], i["source"]) for i in items] == [(2, "user"), (1, "agent")]
    assert "content_md" not in items[0]


async def _save_hld(sessions: Sessions, caller: Any, idea_id: str) -> None:
    """The HLD the Architect wrote for version 1 (its path: the module's service)."""
    workspace_id = UUID(caller.workspace_id)
    async with in_workspace(sessions, workspace_id) as session:
        await ideas.save_spec_hld(
            session,
            workspace_id,
            UUID(idea_id),
            NewSpecHld(
                spec_version_number=1,
                spec_hash=spec_hash(DRAFT),
                build_language="Python",
                content_md="## Overview\n\nA blueprint.",
            ),
        )


async def test_the_overview_carries_the_hld_and_marks_it_stale_after_an_edit(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)
    await _save_hld(app_sessions, ada, idea["id"])

    fresh = (await client.get(_spec(idea["id"]), headers=ada.headers)).json()["hld"]
    assert (await _edit(client, ada, idea["id"], 1)).status_code == 201
    edited = (await client.get(_spec(idea["id"]), headers=ada.headers)).json()["hld"]

    assert (fresh["spec_version_number"], fresh["build_language"]) == (1, "Python")
    assert fresh["content_md"] == "## Overview\n\nA blueprint." and fresh["stale"] is False
    assert (edited["spec_version_number"], edited["stale"]) == (1, True)


async def test_a_version_is_read_by_number_and_an_unknown_one_is_not_found(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)

    found = await client.get(_spec(idea["id"], "/versions/1"), headers=ada.headers)
    missing = await client.get(_spec(idea["id"], "/versions/9"), headers=ada.headers)

    assert found.json()["content_md"] == DRAFT.strip()
    assert_problem(missing, 404, "spec.not_found")


async def test_another_workspace_cannot_see_the_spec(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine, "ada")
    grace = await owner(client, engine, "grace")
    idea = await draft_idea(client, engine, app_sessions, ada)

    response = await client.get(_spec(idea["id"]), headers=grace.headers)

    assert_problem(response, 404, "idea.not_found")


# ------------------------------------------------------------------------------ edit


async def test_an_edit_is_the_next_version_by_the_member_with_sections_parsed(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    bob = await member_of(client, engine, ada)
    idea = await draft_idea(client, engine, app_sessions, ada)
    content = EDITED + "\n\n## Pricing\n\n5 dollars a month."

    response = await _edit(client, bob, idea["id"], 1, content)

    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["number"], body["source"], body["created_by"]) == (2, "user", bob.user_id)
    assert body["content_md"] == content
    assert body["sections"]["pricing"] == "5 dollars a month."
    assert body["sections"]["problem"] == "Freelancers lose track of leads."


async def test_an_edit_from_an_out_of_date_version_is_a_conflict(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)
    assert (await _edit(client, ada, idea["id"], 1)).status_code == 201

    stale = await _edit(client, ada, idea["id"], 1, EDITED + "\nMore.")

    assert_problem(stale, 409, "spec.conflict")
    listed = await client.get(_spec(idea["id"], "/versions"), headers=ada.headers)
    assert [i["number"] for i in listed.json()["items"]] == [2, 1]


async def test_two_edits_from_the_same_version_save_one_and_refuse_the_other(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)

    first, second = await asyncio.gather(
        _edit(client, ada, idea["id"], 1, EDITED + "\nOne."),
        _edit(client, ada, idea["id"], 1, EDITED + "\nTwo."),
    )

    assert sorted([first.status_code, second.status_code]) == [201, 409]
    listed = await client.get(_spec(idea["id"], "/versions"), headers=ada.headers)
    assert [i["number"] for i in listed.json()["items"]] == [2, 1]


async def test_an_idea_without_a_spec_cannot_be_edited(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    await set_stage(engine, idea["id"], "spec_draft")

    response = await _edit(client, ada, idea["id"], 1)

    assert_problem(response, 404, "spec.not_found")


@pytest.mark.parametrize("stage", ["scoring", "spec_confirmed", "planning"])
async def test_the_spec_is_edited_only_while_the_idea_is_a_draft(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions, stage: str
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada, stage=stage)

    response = await _edit(client, ada, idea["id"], 1)

    assert_problem(response, 409, "spec.invalid_transition")


@pytest.mark.parametrize("content", ["", "   ", "x" * 50_001])
async def test_an_empty_or_oversized_edit_is_refused(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions, content: str
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)

    response = await _edit(client, ada, idea["id"], 1, content)

    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------- confirm


async def test_confirming_the_latest_version_fixes_it_and_moves_the_stage(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    app_sessions: Sessions,
    queue: list[dict[str, Any]],
) -> None:
    ada = await owner(client, engine)
    bob = await member_of(client, engine, ada)
    idea = await draft_idea(client, engine, app_sessions, ada)
    assert (await _edit(client, ada, idea["id"], 1)).status_code == 201

    response = await _confirm(client, bob, idea["id"], 2)

    assert response.status_code == 202, response.text
    body = response.json()
    assert (body["confirmed"]["number"], body["run_id"]) == (2, None)
    row = await idea_row(engine, idea["id"])
    assert (row["stage"], str(row["confirmed"])) == ("spec_confirmed", body["confirmed"]["id"])
    events = await spec_confirmed_events(engine, ada)
    assert events == [
        {"idea_id": idea["id"], "spec_version_id": body["confirmed"]["id"], "number": 2}
    ]
    overview = await client.get(_spec(idea["id"]), headers=ada.headers)
    assert overview.json()["confirmed"]["number"] == 2
    assert queue == []


async def test_confirming_an_older_version_is_a_conflict(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)
    assert (await _edit(client, ada, idea["id"], 1)).status_code == 201

    response = await _confirm(client, ada, idea["id"], 1)

    assert_problem(response, 409, "spec.conflict")
    assert (await idea_row(engine, idea["id"]))["stage"] == "spec_draft"
    assert await spec_confirmed_events(engine, ada) == []


async def test_confirming_twice_writes_one_event(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)
    assert (await _confirm(client, ada, idea["id"], 1)).status_code == 202

    again = await _confirm(client, ada, idea["id"], 1)

    assert again.status_code == 202, again.text
    assert len(await spec_confirmed_events(engine, ada)) == 1


async def test_two_confirmations_at_once_write_one_event(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)

    first, second = await asyncio.gather(
        _confirm(client, ada, idea["id"], 1), _confirm(client, ada, idea["id"], 1)
    )

    assert (first.status_code, second.status_code) == (202, 202)
    assert len(await spec_confirmed_events(engine, ada)) == 1


async def test_an_edit_and_a_confirmation_at_once_leave_one_consistent_outcome(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)

    edit, confirm = await asyncio.gather(
        _edit(client, ada, idea["id"], 1), _confirm(client, ada, idea["id"], 1)
    )

    listed = await client.get(_spec(idea["id"], "/versions"), headers=ada.headers)
    numbers = [i["number"] for i in listed.json()["items"]]
    if confirm.status_code == 202:  # confirmed first: the edit came too late
        assert edit.status_code == 409
        assert numbers == [1]
        assert (await idea_row(engine, idea["id"]))["stage"] == "spec_confirmed"
    else:  # edited first: version 1 is no longer the latest
        assert (edit.status_code, confirm.status_code) == (201, 409)
        assert numbers == [2, 1]
        assert (await idea_row(engine, idea["id"]))["stage"] == "spec_draft"
    assert len(await spec_confirmed_events(engine, ada)) == (confirm.status_code == 202)


async def test_a_confirmed_spec_cannot_be_edited(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)
    assert (await _confirm(client, ada, idea["id"], 1)).status_code == 202

    response = await _edit(client, ada, idea["id"], 1)

    assert_problem(response, 409, "spec.invalid_transition")


async def test_an_idea_at_another_stage_cannot_be_confirmed(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada, stage="scoring")

    response = await _confirm(client, ada, idea["id"], 1)

    assert_problem(response, 409, "spec.invalid_transition")


async def test_confirming_resumes_the_run_waiting_on_the_review(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    app_sessions: Sessions,
    queue: list[dict[str, Any]],
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)
    run_id = await waiting_run(engine, ada, idea["id"])

    response = await _confirm(client, ada, idea["id"], 1)

    assert response.json()["run_id"] == run_id
    assert len(queue) == 1
    call = queue[0]
    assert (call["job"], call["run_id"], call["workspace_id"]) == (
        "run_graph",
        run_id,
        ada.workspace_id,
    )
    assert call["resume"] == {"confirmed_number": 1}
    assert call["job_id"].startswith(f"{run_id}:resume:")


async def test_a_failed_enqueue_keeps_the_confirmation_and_a_retry_enqueues_again(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    app_sessions: Sessions,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)
    await waiting_run(engine, ada, idea["id"])

    async def broken(job_name: str, *args: Any, **kwargs: Any) -> None:
        raise ConnectionError("redis is down")

    monkeypatch.setattr(jobs, "enqueue", broken)

    failed = await _confirm(client, ada, idea["id"], 1)

    assert_problem(failed, 503, "run.enqueue_failed")
    assert (await idea_row(engine, idea["id"]))["stage"] == "spec_confirmed"
    calls: list[dict[str, Any]] = []

    async def fake_enqueue(job_name: str, *args: Any, **kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(jobs, "enqueue", fake_enqueue)

    retried = await _confirm(client, ada, idea["id"], 1)

    assert retried.status_code == 202, retried.text
    assert [c["resume"] for c in calls] == [{"confirmed_number": 1}]
    assert len(await spec_confirmed_events(engine, ada)) == 1


async def test_a_run_waiting_on_the_review_cannot_be_resumed_through_the_run_route(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await owner(client, engine)
    idea = await draft_idea(client, engine, app_sessions, ada)
    run_id = await waiting_run(engine, ada, idea["id"])

    for value in (True, "confirm"):
        response = await client.post(
            f"/v1/runs/{run_id}/resume", json={"value": value}, headers=ada.headers
        )

        assert response.status_code == 422, response.text
    async with engine.connect() as conn:
        status = await conn.scalar(
            text("SELECT status FROM ideas.workflow_runs WHERE id = :id"), {"id": run_id}
        )
    assert status == "awaiting_user"
