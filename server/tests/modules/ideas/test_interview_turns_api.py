"""``GET /v1/ideas/{id}/interview`` at the HTTP seam.

Real app, real Postgres (request session as ``metis_app``, so RLS applies) and Redis. Turns
are written through the ideas module's public functions, as the Interviewer's tools do.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import httpx
from idea_helpers import IDEAS_URL, Caller, create, owner
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.core.db import set_workspace
from metis.core.errors import ErrorCode
from metis.modules import ideas
from metis.modules.ideas import InterviewTopic
from tests.helpers.auth import assert_problem


@asynccontextmanager
async def _session(
    sessions: async_sessionmaker[AsyncSession], caller: Caller
) -> AsyncGenerator[AsyncSession]:
    async with sessions() as session, session.begin():
        await set_workspace(session, UUID(caller.workspace_id))
        yield session


async def _start_run(client: httpx.AsyncClient, caller: Caller, idea_id: str) -> UUID:
    headers = {**caller.headers, "Idempotency-Key": uuid4().hex}
    response = await client.post(f"{IDEAS_URL}/{idea_id}/runs", headers=headers)
    assert response.status_code == 202, response.text
    return UUID(response.json()["run_id"])


async def _ask(
    sessions: async_sessionmaker[AsyncSession],
    caller: Caller,
    idea_id: str,
    run_id: UUID,
    topic: InterviewTopic,
    question: str,
    answer: str | None = None,
) -> None:
    workspace_id = UUID(caller.workspace_id)
    async with _session(sessions, caller) as session:
        turn = await ideas.open_question(
            session, workspace_id, UUID(idea_id), run_id, topic, question
        )
        assert isinstance(turn, ideas.InterviewTurn)
        if answer is not None:
            await ideas.answer_question(session, workspace_id, turn.id, answer)


def _url(idea_id: str) -> str:
    return f"{IDEAS_URL}/{idea_id}/interview"


async def _turns(client: httpx.AsyncClient, caller: Caller, idea_id: str) -> list[Any]:
    response = await client.get(_url(idea_id), headers=caller.headers)
    assert response.status_code == 200, response.text
    items: list[Any] = response.json()["items"]
    return items


async def test_turns_come_back_oldest_first_with_the_open_question_unanswered(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    run_id = await _start_run(client, ada, idea["id"])
    await _ask(
        app_sessions,
        ada,
        idea["id"],
        run_id,
        InterviewTopic.PROBLEM,
        "Who feels it?",
        "Freelancers",
    )
    await _ask(app_sessions, ada, idea["id"], run_id, InterviewTopic.PAYMENT, "Who pays?")

    turns = await _turns(client, ada, idea["id"])

    assert [(t["question"], t["answer"]) for t in turns] == [
        ("Who feels it?", "Freelancers"),
        ("Who pays?", None),
    ]
    assert turns[0]["topic"] == "problem"
    assert turns[0]["source"] == "asked"
    assert turns[0]["idea_id"] == idea["id"]
    assert turns[0]["run_id"] == str(run_id)


async def test_noted_turns_are_listed_with_their_source(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    run_id = await _start_run(client, ada, idea["id"])
    async with _session(app_sessions, ada) as session:
        await ideas.save_interview_turn(
            session,
            UUID(ada.workspace_id),
            UUID(idea["id"]),
            run_id,
            InterviewTopic.CUSTOMER,
            "Who is it for?",
            "Freelancers",
        )

    turns = await _turns(client, ada, idea["id"])

    assert [(t["source"], t["topic"]) for t in turns] == [("noted", "customer")]


async def test_turns_of_every_run_of_the_idea_appear_in_one_list(
    client: httpx.AsyncClient, engine: AsyncEngine, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    first_run = await _start_run(client, ada, idea["id"])
    await _ask(
        app_sessions, ada, idea["id"], first_run, InterviewTopic.PROBLEM, "Who?", "Freelancers"
    )
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE ideas.workflow_runs SET status = 'failed' WHERE id = :id"),
            {"id": first_run},
        )
    second_run = await _start_run(client, ada, idea["id"])
    await _ask(app_sessions, ada, idea["id"], second_run, InterviewTopic.PAYMENT, "Who pays?")

    turns = await _turns(client, ada, idea["id"])

    assert [t["run_id"] for t in turns] == [str(first_run), str(second_run)]


async def test_an_idea_without_turns_returns_an_empty_list(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)

    response = await client.get(_url(idea["id"]), headers=ada.headers)

    assert response.status_code == 200, response.text
    assert response.json() == {"items": []}


async def test_another_workspace_gets_a_404(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ada = await owner(client, engine, "ada")
    bob = await owner(client, engine, "bob")
    idea = await create(client, ada)

    response = await client.get(_url(idea["id"]), headers=bob.headers)

    assert_problem(response, 404, ErrorCode.IDEA_NOT_FOUND)


async def test_an_archived_idea_gets_a_404(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    deleted = await client.delete(f"{IDEAS_URL}/{idea['id']}", headers=ada.headers)
    assert deleted.status_code == 204

    response = await client.get(_url(idea["id"]), headers=ada.headers)

    assert_problem(response, 404, ErrorCode.IDEA_NOT_FOUND)


async def test_an_unknown_idea_gets_a_404(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    ada = await owner(client, engine)

    response = await client.get(_url(str(uuid4())), headers=ada.headers)

    assert_problem(response, 404, ErrorCode.IDEA_NOT_FOUND)


async def test_a_caller_without_a_session_gets_a_401(client: httpx.AsyncClient) -> None:
    response = await client.get(_url(str(uuid4())))

    assert_problem(response, 401, ErrorCode.NOT_SIGNED_IN)
