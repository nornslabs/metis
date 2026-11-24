"""Run routes (start, resume, cancel, get, list) at the HTTP seam.

Real app, real Postgres (request session as ``metis_app``, so RLS applies) and Redis. The
queue is a recording fake of ``core.jobs.enqueue``; the job itself is covered by SHIP-228.
The fake also reads the run row on its own connection, so a test sees whether the run was
committed by the time the job was queued.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from idea_helpers import Caller, create, member_of, owner
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.core import events, jobs
from metis.core.errors import ErrorCode
from metis.core.run_control import cancel_key
from tests.helpers.auth import CLIENT_HEADER, assert_problem

ACTIVE = ["queued", "running", "awaiting_user"]
TERMINAL = ["succeeded", "failed", "cancelled"]
QUESTION = {"type": "question", "question": "Who is it for?"}
APPROVAL = {"type": "approval", "action": "create_issue", "details": "Create SHIP-1"}
PHASE_REVIEW = {"type": "phase_review", "phases": []}
CHOOSE_TEAM = {
    "type": "choose_team",
    "teams": [
        {"id": "team-1", "name": "Product", "key": "PRD"},
        {"id": "team-2", "name": "Platform", "key": "PLT"},
    ],
    "saved_team_id": None,
}
EXPORT_APPROVAL = {"type": "export_approval", "preview": {}}
PHASES = [
    {"name": "Foundations", "goal": "Set up.", "exit_criteria": "Base runs."},
    {"name": "Launch", "goal": "Ship.", "exit_criteria": "Live."},
]
ADVICE = {"type": "advice_decision", "score_run_id": str(uuid4()), "total": 40, "band": "advise"}


@pytest.fixture
def queue(monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine) -> list[dict[str, Any]]:
    """Every ``enqueue`` call, with whether the run row was visible to another connection."""
    calls: list[dict[str, Any]] = []

    async def fake_enqueue(job_name: str, *args: Any, **kwargs: Any) -> None:
        async with engine.connect() as conn:
            visible = await conn.scalar(
                text("SELECT count(*) FROM ideas.workflow_runs WHERE id = :id"),
                {"id": kwargs["run_id"]},
            )
        calls.append({"job": job_name, "row_visible": visible == 1, **kwargs})

    monkeypatch.setattr(jobs, "enqueue", fake_enqueue)
    return calls


def _key() -> dict[str, str]:
    return {"Idempotency-Key": uuid4().hex}


async def _start(
    client: httpx.AsyncClient, caller: Caller, idea_id: str, key: str | None = None
) -> httpx.Response:
    headers = {**caller.headers, "Idempotency-Key": key or uuid4().hex}
    return await client.post(f"/v1/ideas/{idea_id}/runs", headers=headers)


async def _new_run(client: httpx.AsyncClient, caller: Caller, idea_id: str) -> str:
    response = await _start(client, caller, idea_id)
    assert response.status_code == 202, response.text
    return str(response.json()["run_id"])


async def _set(engine: AsyncEngine, run_id: str, status: str, interrupt: Any = None) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ideas.workflow_runs SET status = :s, version = version + 1, "
                "pending_interrupt = CAST(:i AS jsonb) WHERE id = :id"
            ),
            {"s": status, "id": run_id, "i": None if interrupt is None else json.dumps(interrupt)},
        )


async def _run_count(engine: AsyncEngine, idea_id: str) -> int:
    async with engine.connect() as conn:
        count = await conn.scalar(
            text("SELECT count(*) FROM ideas.workflow_runs WHERE idea_id = :id"), {"id": idea_id}
        )
    return int(count or 0)


async def _status(engine: AsyncEngine, run_id: str) -> str:
    async with engine.connect() as conn:
        return str(
            await conn.scalar(
                text("SELECT status FROM ideas.workflow_runs WHERE id = :id"), {"id": run_id}
            )
        )


async def _ready(client: httpx.AsyncClient, engine: AsyncEngine) -> tuple[Caller, str]:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    return ada, str(idea["id"])


# ------------------------------------------------------------------------------ start


async def test_start_queues_a_run_and_enqueues_it_after_the_commit(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)

    response = await _start(client, ada, idea_id)

    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    assert await _status(engine, run_id) == "queued"
    assert queue == [
        {
            "job": "run_graph",
            "row_visible": True,
            "run_id": run_id,
            "workspace_id": ada.workspace_id,
            "job_id": run_id,
        }
    ]


async def test_the_same_key_returns_the_same_run(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)
    key = uuid4().hex

    first = await _start(client, ada, idea_id, key)
    second = await _start(client, ada, idea_id, key)

    assert second.status_code == 202
    assert second.json() == first.json()
    assert await _run_count(engine, idea_id) == 1
    assert {call["job_id"] for call in queue} == {first.json()["run_id"]}  # Arq dedupes this


async def test_a_concurrent_double_submit_creates_one_run(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)
    key = uuid4().hex

    first, second = await asyncio.gather(
        _start(client, ada, idea_id, key), _start(client, ada, idea_id, key)
    )

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert await _run_count(engine, idea_id) == 1


async def test_concurrent_starts_with_different_keys_leave_one_active_run(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)

    responses = await asyncio.gather(*(_start(client, ada, idea_id) for _ in range(3)))

    codes = sorted(r.status_code for r in responses)
    assert codes == [202, 409, 409]
    assert await _run_count(engine, idea_id) == 1


@pytest.mark.parametrize("key", ["", "has space", "x" * 256])
async def test_a_bad_idempotency_key_is_422(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]], key: str
) -> None:
    ada, idea_id = await _ready(client, engine)

    response = await client.post(
        f"/v1/ideas/{idea_id}/runs", headers={**ada.headers, "Idempotency-Key": key}
    )

    assert_problem(response, 422, ErrorCode.VALIDATION_FAILED)
    assert queue == []


async def test_a_missing_idempotency_key_is_422(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)

    response = await client.post(f"/v1/ideas/{idea_id}/runs", headers=ada.headers)

    assert_problem(response, 422, ErrorCode.VALIDATION_FAILED)


async def test_a_key_used_on_another_idea_is_a_409(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)
    other = str((await create(client, ada, title="Second idea"))["id"])
    key = uuid4().hex
    await _start(client, ada, idea_id, key)

    response = await _start(client, ada, other, key)

    assert_problem(response, 409, ErrorCode.RUN_IDEMPOTENCY_MISMATCH)
    assert await _run_count(engine, other) == 0


@pytest.mark.parametrize("status", ACTIVE)
async def test_an_active_run_blocks_a_new_one(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]], status: str
) -> None:
    ada, idea_id = await _ready(client, engine)
    run_id = await _new_run(client, ada, idea_id)
    await _set(engine, run_id, status, QUESTION if status == "awaiting_user" else None)

    response = await _start(client, ada, idea_id)

    assert_problem(response, 409, ErrorCode.RUN_ALREADY_RUNNING)
    assert await _run_count(engine, idea_id) == 1


@pytest.mark.parametrize("status", TERMINAL)
async def test_a_finished_run_does_not_block_a_new_one(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]], status: str
) -> None:
    ada, idea_id = await _ready(client, engine)
    await _set(engine, await _new_run(client, ada, idea_id), status)

    response = await _start(client, ada, idea_id)

    assert response.status_code == 202, response.text
    assert await _run_count(engine, idea_id) == 2


async def test_start_on_an_unknown_archived_or_foreign_idea_is_404(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)
    grace = await owner(client, engine, "grace")
    archived = str((await create(client, ada, title="Archived idea"))["id"])
    await client.delete(f"/v1/ideas/{archived}", headers=ada.headers)

    for target, caller in [(str(uuid4()), ada), (archived, ada), (idea_id, grace)]:
        assert_problem(await _start(client, caller, target), 404, ErrorCode.IDEA_NOT_FOUND)
    assert queue == []


async def test_a_workspace_member_can_start_a_run(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)
    bob = await member_of(client, engine, ada)

    assert (await _start(client, bob, idea_id)).status_code == 202


async def test_a_failed_enqueue_is_503_and_a_retry_with_the_same_key_queues_it(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queue: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ada, idea_id = await _ready(client, engine)
    key = uuid4().hex
    working = jobs.enqueue

    async def broken(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("redis is down")

    monkeypatch.setattr(jobs, "enqueue", broken)
    failed = await _start(client, ada, idea_id, key)
    monkeypatch.setattr(jobs, "enqueue", working)
    retry = await _start(client, ada, idea_id, key)

    assert_problem(failed, 503, ErrorCode.RUN_ENQUEUE_FAILED)
    assert retry.status_code == 202
    assert await _run_count(engine, idea_id) == 1
    assert [call["run_id"] for call in queue] == [retry.json()["run_id"]]


async def test_a_mutation_without_the_client_header_is_403(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)
    headers = {k: v for k, v in ada.headers.items() if k != CLIENT_HEADER}

    response = await client.post(f"/v1/ideas/{idea_id}/runs", headers={**headers, **_key()})

    assert_problem(response, 403, ErrorCode.CSRF_FAILED)


# ----------------------------------------------------------------------------- resume


async def _waiting(
    client: httpx.AsyncClient, engine: AsyncEngine, interrupt: dict[str, Any]
) -> tuple[Caller, str]:
    ada, idea_id = await _ready(client, engine)
    run_id = await _new_run(client, ada, idea_id)
    await _set(engine, run_id, "awaiting_user", interrupt)
    return ada, run_id


async def _resume(
    client: httpx.AsyncClient, caller: Caller, run_id: str, value: Any
) -> httpx.Response:
    return await client.post(
        f"/v1/runs/{run_id}/resume", json={"value": value}, headers=caller.headers
    )


async def test_resume_answers_a_question_and_enqueues_the_job_with_the_value(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, run_id = await _waiting(client, engine, QUESTION)
    queue.clear()

    response = await _resume(client, ada, run_id, "  Freelancers  ")

    assert response.status_code == 202, response.text
    assert response.json() == {"run_id": run_id}
    [call] = queue
    assert call["resume"] == "Freelancers"
    assert call["run_id"] == run_id
    assert call["workspace_id"] == ada.workspace_id
    assert call["job_id"].startswith(f"{run_id}:resume:")


async def test_resume_carries_an_advice_decision_with_its_revision(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, run_id = await _waiting(client, engine, ADVICE)
    queue.clear()
    suggestion_id = "0197d4a2-3b1c-7f00-8a00-000000000001"
    value = {
        "decision": "revise",
        "revised_text": "  A CRM for freelancers that also sends invoices.  ",
        "accepted_suggestion_ids": [suggestion_id],
    }

    response = await _resume(client, ada, run_id, value)

    assert response.status_code == 202, response.text
    assert queue[0]["resume"] == {
        "decision": "revise",
        "revised_text": "  A CRM for freelancers that also sends invoices.  ",
        "accepted_suggestion_ids": [suggestion_id],
    }


@pytest.mark.parametrize("decision", ["continue", "stop"])
async def test_resume_carries_a_continue_or_stop_decision(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queue: list[dict[str, Any]],
    decision: str,
) -> None:
    ada, run_id = await _waiting(client, engine, ADVICE)
    queue.clear()

    response = await _resume(client, ada, run_id, {"decision": decision})

    assert response.status_code == 202, response.text
    assert queue[0]["resume"]["decision"] == decision


@pytest.mark.parametrize(
    "value",
    [
        {"decision": "revise"},
        {"decision": "revise", "revised_text": "short"},
        {"decision": "revise", "revised_text": "x" * 10_001},
        {"decision": "maybe"},
        {"decision": "continue", "accepted_suggestion_ids": ["not-a-uuid"]},
        {"decision": "continue", "accepted_suggestion_ids": [str(uuid4()) for _ in range(6)]},
        {"decision": "continue", "extra": 1},
        "continue",
        True,
    ],
)
async def test_an_advice_value_that_does_not_fit_is_422(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queue: list[dict[str, Any]],
    value: Any,
) -> None:
    ada, run_id = await _waiting(client, engine, ADVICE)
    queue.clear()

    response = await _resume(client, ada, run_id, value)

    assert response.status_code == 422, response.text
    assert queue == []


@pytest.mark.parametrize("interrupt", [QUESTION, APPROVAL])
async def test_an_advice_decision_does_not_answer_a_question_or_approval(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queue: list[dict[str, Any]],
    interrupt: dict[str, Any],
) -> None:
    ada, run_id = await _waiting(client, engine, interrupt)
    queue.clear()

    response = await _resume(client, ada, run_id, {"decision": "continue"})

    assert_problem(response, 422, ErrorCode.VALIDATION_FAILED)
    assert queue == []


async def test_resume_carries_the_reviewed_phases(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, run_id = await _waiting(client, engine, PHASE_REVIEW)
    queue.clear()
    edited = [{**PHASES[0], "name": "  Base  "}, PHASES[1]]

    response = await _resume(client, ada, run_id, {"phases": edited})

    assert response.status_code == 202, response.text
    assert queue[0]["resume"] == {"phases": [{**PHASES[0], "name": "Base"}, PHASES[1]]}


@pytest.mark.parametrize(
    "value",
    [
        {"phases": []},
        {"phases": [PHASES[0]] * 13},
        {"phases": [{**PHASES[0], "name": ""}]},
        {"phases": [{**PHASES[0], "name": "x" * 121}]},
        {"phases": [{**PHASES[0], "goal": "x" * 1_001}]},
        {"phases": [{"name": "Only a name"}]},
        {"phases": PHASES, "extra": 1},
        "approve",
        True,
    ],
)
async def test_a_phase_review_value_that_does_not_fit_is_422(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queue: list[dict[str, Any]],
    value: Any,
) -> None:
    ada, run_id = await _waiting(client, engine, PHASE_REVIEW)
    queue.clear()

    response = await _resume(client, ada, run_id, value)

    assert response.status_code == 422, response.text
    assert queue == []


@pytest.mark.parametrize("interrupt", [QUESTION, APPROVAL, ADVICE])
async def test_reviewed_phases_do_not_answer_another_kind_of_interrupt(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queue: list[dict[str, Any]],
    interrupt: dict[str, Any],
) -> None:
    ada, run_id = await _waiting(client, engine, interrupt)
    queue.clear()

    response = await _resume(client, ada, run_id, {"phases": PHASES})

    assert_problem(response, 422, ErrorCode.VALIDATION_FAILED)
    assert queue == []


async def test_resume_carries_an_approval_decision(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, run_id = await _waiting(client, engine, APPROVAL)
    queue.clear()

    response = await _resume(client, ada, run_id, False)

    assert response.status_code == 202, response.text
    assert queue[0]["resume"] is False


@pytest.mark.parametrize(
    ("interrupt", "value"),
    [
        (QUESTION, True),
        (QUESTION, "   "),
        (QUESTION, "x" * 10_001),
        (QUESTION, 7),
        (APPROVAL, "yes"),
        (APPROVAL, None),
    ],
)
async def test_a_value_that_does_not_fit_the_interrupt_is_422(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queue: list[dict[str, Any]],
    interrupt: dict[str, Any],
    value: Any,
) -> None:
    ada, run_id = await _waiting(client, engine, interrupt)
    queue.clear()

    response = await _resume(client, ada, run_id, value)

    assert_problem(response, 422, ErrorCode.VALIDATION_FAILED)
    assert queue == []


OPTIONS_QUESTION = {
    "type": "question",
    "question": "Who is it for?",
    "multi": False,
    "options": [
        {"id": "o1", "label": "Solo freelancers", "recommended": True},
        {"id": "o2", "label": "Small agencies", "recommended": False},
        {"id": "o3", "label": "In-house teams", "recommended": False},
    ],
    "allow_free_text": True,
    "index": 1,
    "total": 5,
}
MULTI_QUESTION = {**OPTIONS_QUESTION, "multi": True}
PICK_ONLY_QUESTION = {**OPTIONS_QUESTION, "allow_free_text": False}


@pytest.mark.parametrize(
    ("interrupt", "value", "answer"),
    [
        (OPTIONS_QUESTION, {"option_ids": ["o2"]}, "Small agencies"),
        (MULTI_QUESTION, {"option_ids": ["o3", "o1"]}, "Solo freelancers; In-house teams"),
        (OPTIONS_QUESTION, {"text": "  Students  "}, "Students"),
        (OPTIONS_QUESTION, "  Students  ", "Students"),
        (PICK_ONLY_QUESTION, {"option_ids": ["o1"]}, "Solo freelancers"),
        (QUESTION, {"text": "Freelancers"}, "Freelancers"),
    ],
)
async def test_resume_turns_a_picked_option_or_typed_text_into_the_answer(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queue: list[dict[str, Any]],
    interrupt: dict[str, Any],
    value: Any,
    answer: str,
) -> None:
    ada, run_id = await _waiting(client, engine, interrupt)
    queue.clear()

    response = await _resume(client, ada, run_id, value)

    assert response.status_code == 202, response.text
    [call] = queue
    assert call["resume"] == answer


@pytest.mark.parametrize(
    ("interrupt", "value"),
    [
        (OPTIONS_QUESTION, {"option_ids": ["o9"]}),
        (OPTIONS_QUESTION, {"option_ids": []}),
        (OPTIONS_QUESTION, {}),
        (OPTIONS_QUESTION, {"option_ids": ["o1", "o2"]}),
        (MULTI_QUESTION, {"option_ids": ["o1", "o1"]}),
        (MULTI_QUESTION, {"option_ids": ["o1", "o9"]}),
        (OPTIONS_QUESTION, {"option_ids": ["o1"], "text": "Students"}),
        (OPTIONS_QUESTION, {"text": "   "}),
        (OPTIONS_QUESTION, {"text": "x" * 10_001}),
        (OPTIONS_QUESTION, {"option_ids": ["o1"], "extra": 1}),
        (PICK_ONLY_QUESTION, {"text": "Students"}),
        (PICK_ONLY_QUESTION, "Students"),
        (QUESTION, {"option_ids": ["o1"]}),
    ],
)
async def test_a_question_answer_that_does_not_fit_is_422(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queue: list[dict[str, Any]],
    interrupt: dict[str, Any],
    value: Any,
) -> None:
    ada, run_id = await _waiting(client, engine, interrupt)
    queue.clear()

    response = await _resume(client, ada, run_id, value)

    assert_problem(response, 422, ErrorCode.VALIDATION_FAILED)
    assert queue == []


async def test_an_unknown_option_id_is_reported_on_the_value_field(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, run_id = await _waiting(client, engine, OPTIONS_QUESTION)
    queue.clear()

    response = await _resume(client, ada, run_id, {"option_ids": ["o9"]})

    assert_problem(response, 422, ErrorCode.VALIDATION_FAILED)
    assert response.json()["errors"][0]["field"] == "body.value"
    assert queue == []


@pytest.mark.parametrize("interrupt", [APPROVAL, ADVICE, PHASE_REVIEW])
async def test_picked_options_do_not_answer_another_kind_of_interrupt(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queue: list[dict[str, Any]],
    interrupt: dict[str, Any],
) -> None:
    ada, run_id = await _waiting(client, engine, interrupt)
    queue.clear()

    response = await _resume(client, ada, run_id, {"option_ids": ["o1"]})

    assert_problem(response, 422, ErrorCode.VALIDATION_FAILED)
    assert queue == []


@pytest.mark.parametrize("status", ["queued", "running", *TERMINAL])
async def test_resume_on_a_run_that_is_not_waiting_is_409(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]], status: str
) -> None:
    ada, idea_id = await _ready(client, engine)
    run_id = await _new_run(client, ada, idea_id)
    await _set(engine, run_id, status)
    queue.clear()

    response = await _resume(client, ada, run_id, "an answer")

    assert_problem(response, 409, ErrorCode.RUN_INVALID_STATE)
    assert queue == []


async def test_a_double_submitted_resume_uses_one_job_id(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, run_id = await _waiting(client, engine, QUESTION)
    queue.clear()

    await _resume(client, ada, run_id, "Freelancers")
    await _resume(client, ada, run_id, "Freelancers")

    assert len({call["job_id"] for call in queue}) == 1


async def test_a_later_pause_gets_a_new_resume_job_id(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, run_id = await _waiting(client, engine, QUESTION)
    queue.clear()
    await _resume(client, ada, run_id, "first")
    await _set(engine, run_id, "running")
    await _set(engine, run_id, "awaiting_user", QUESTION)

    await _resume(client, ada, run_id, "second")

    assert queue[0]["job_id"] != queue[1]["job_id"]


# ------------------------------------------------------------------------------ cancel


async def _cancel(client: httpx.AsyncClient, caller: Caller, run_id: str) -> httpx.Response:
    return await client.post(f"/v1/runs/{run_id}/cancel", headers=caller.headers)


async def _events(redis: Redis, run_id: str) -> list[dict[str, str]]:
    entries = await redis.xrange(events.stream_key(run_id))
    return [{k.decode(): v.decode() for k, v in fields.items()} for _id, fields in entries]


@pytest.mark.parametrize("status", ["queued", "awaiting_user"])
async def test_cancel_stops_a_queued_or_waiting_run_at_once(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    redis: Redis,
    queue: list[dict[str, Any]],
    status: str,
) -> None:
    ada, idea_id = await _ready(client, engine)
    run_id = await _new_run(client, ada, idea_id)
    await _set(engine, run_id, status, QUESTION if status == "awaiting_user" else None)

    response = await _cancel(client, ada, run_id)

    assert response.status_code == 202, response.text
    assert response.json() == {"run_id": run_id, "status": "cancelled"}
    assert await _status(engine, run_id) == "cancelled"
    assert await redis.exists(cancel_key(run_id)) == 1
    [event] = await _events(redis, run_id)
    assert event["type"] == "run_status"
    assert '"cancelled"' in event["data"]


async def test_cancel_of_a_running_run_only_sets_the_flag(
    client: httpx.AsyncClient, engine: AsyncEngine, redis: Redis, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)
    run_id = await _new_run(client, ada, idea_id)
    await _set(engine, run_id, "running")

    response = await _cancel(client, ada, run_id)

    assert response.status_code == 202
    assert response.json() == {"run_id": run_id, "status": "running"}
    assert await _status(engine, run_id) == "running"
    assert await redis.exists(cancel_key(run_id)) == 1
    assert await _events(redis, run_id) == []


@pytest.mark.parametrize("status", ["succeeded", "failed"])
async def test_cancel_of_a_finished_run_is_409_and_sets_no_flag(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    redis: Redis,
    queue: list[dict[str, Any]],
    status: str,
) -> None:
    ada, idea_id = await _ready(client, engine)
    run_id = await _new_run(client, ada, idea_id)
    await _set(engine, run_id, status)

    response = await _cancel(client, ada, run_id)

    assert_problem(response, 409, ErrorCode.RUN_INVALID_STATE)
    assert await redis.exists(cancel_key(run_id)) == 0


async def test_cancelling_a_cancelled_run_again_is_accepted(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)
    run_id = await _new_run(client, ada, idea_id)
    await _cancel(client, ada, run_id)

    response = await _cancel(client, ada, run_id)

    assert response.status_code == 202
    assert response.json()["status"] == "cancelled"


# ------------------------------------------------------------------------- get / list


async def test_get_shows_status_stage_interrupt_and_no_internals(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, run_id = await _waiting(client, engine, QUESTION)

    response = await client.get(f"/v1/runs/{run_id}", headers=ada.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == run_id
    assert body["status"] == "awaiting_user"
    assert body["stage"] == "intake"
    assert body["pending_interrupt"] == QUESTION
    assert body["error"] is None
    assert "kind" in body  # RunView now includes kind
    assert not {"workspace_id", "idempotency_key"} & body.keys()


async def test_get_shows_the_ideas_live_stage_and_the_error_of_a_failed_run(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)
    run_id = await _new_run(client, ada, idea_id)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE ideas.ideas SET stage = 'researching' WHERE id = :id"), {"id": idea_id}
        )
        await conn.execute(
            text(
                "UPDATE ideas.workflow_runs SET status = 'failed', "
                'error = \'{"code": "run.failed", "message": "Run Failed"}\' '
                "WHERE id = :id"
            ),
            {"id": run_id},
        )

    body = (await client.get(f"/v1/runs/{run_id}", headers=ada.headers)).json()

    assert body["stage"] == "researching"
    assert body["error"] == {"code": "run.failed", "message": "Run Failed"}
    assert body["pending_interrupt"] is None


async def test_a_run_of_another_workspace_is_404_on_every_route(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)
    run_id = await _new_run(client, ada, idea_id)
    await _set(engine, run_id, "awaiting_user", QUESTION)
    grace = await owner(client, engine, "grace")

    responses = [
        await client.get(f"/v1/runs/{run_id}", headers=grace.headers),
        await _resume(client, grace, run_id, "hi"),
        await _cancel(client, grace, run_id),
        await client.get(f"/v1/ideas/{idea_id}/runs", headers=grace.headers),
    ]

    codes = [r.json()["code"] for r in responses]
    assert [r.status_code for r in responses] == [404, 404, 404, 404]
    assert codes == ["run.not_found"] * 3 + ["idea.not_found"]


async def test_list_pages_runs_newest_first(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)
    ids = []
    for _ in range(3):
        run_id = await _new_run(client, ada, idea_id)
        await _set(engine, run_id, "succeeded")
        ids.append(run_id)

    first = (
        await client.get(f"/v1/ideas/{idea_id}/runs", params={"limit": 2}, headers=ada.headers)
    ).json()
    second = (
        await client.get(
            f"/v1/ideas/{idea_id}/runs",
            params={"limit": 2, "cursor": first["next_cursor"]},
            headers=ada.headers,
        )
    ).json()

    assert [item["id"] for item in first["items"]] == [ids[2], ids[1]]
    assert first["next_cursor"] is not None
    assert [item["id"] for item in second["items"]] == [ids[0]]
    assert second["next_cursor"] is None


async def test_list_with_a_bad_cursor_is_422_and_an_unknown_idea_is_404(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)

    bad = await client.get(
        f"/v1/ideas/{idea_id}/runs", params={"cursor": "nope"}, headers=ada.headers
    )
    unknown = await client.get(f"/v1/ideas/{uuid4()}/runs", headers=ada.headers)

    assert_problem(bad, 422, ErrorCode.VALIDATION_FAILED)
    assert_problem(unknown, 404, ErrorCode.IDEA_NOT_FOUND)


async def test_unauthenticated_get_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/v1/runs/{uuid4()}", headers={"X-Metis-Client": "web"})

    assert_problem(response, 401, ErrorCode.NOT_SIGNED_IN)


async def test_starting_a_run_moves_the_idea_to_the_top_of_the_list_without_a_new_version(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, idea_id = await _ready(client, engine)
    other = await create(client, ada, title="Created after the first idea")
    before = (await client.get("/v1/ideas", headers=ada.headers)).json()["items"]
    assert [i["id"] for i in before][0] == other["id"]
    version = next(i["version"] for i in before if i["id"] == idea_id)

    assert (await _start(client, ada, idea_id)).status_code == 202

    after = (await client.get("/v1/ideas", headers=ada.headers)).json()["items"]
    assert [i["id"] for i in after][0] == idea_id
    assert next(i["version"] for i in after if i["id"] == idea_id) == version


async def test_resume_carries_the_chosen_team(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, run_id = await _waiting(client, engine, CHOOSE_TEAM)
    queue.clear()

    response = await _resume(client, ada, run_id, {"team_id": "team-2"})

    assert response.status_code == 202, response.text
    assert queue[0]["resume"] == {"team_id": "team-2"}


@pytest.mark.parametrize(
    "value",
    [{"team_id": "team-9"}, {"team_id": ""}, {"team_id": 2}, {"team_id": "team-1", "x": 1}, True],
)
async def test_a_team_choice_that_was_not_offered_or_does_not_fit_is_422(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queue: list[dict[str, Any]],
    value: Any,
) -> None:
    ada, run_id = await _waiting(client, engine, CHOOSE_TEAM)
    queue.clear()

    response = await _resume(client, ada, run_id, value)

    assert_problem(response, 422, ErrorCode.VALIDATION_FAILED)
    assert queue == []


@pytest.mark.parametrize("approved", [True, False])
async def test_an_export_approval_is_stamped_with_the_user_who_answered(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queue: list[dict[str, Any]],
    approved: bool,
) -> None:
    ada, run_id = await _waiting(client, engine, EXPORT_APPROVAL)
    queue.clear()

    response = await _resume(client, ada, run_id, {"approved": approved})

    assert response.status_code == 202, response.text
    assert queue[0]["resume"] == {"approved": approved, "decided_by": ada.user_id}


async def test_the_approver_cannot_be_named_in_the_request(
    client: httpx.AsyncClient, engine: AsyncEngine, queue: list[dict[str, Any]]
) -> None:
    ada, run_id = await _waiting(client, engine, EXPORT_APPROVAL)
    queue.clear()

    response = await _resume(client, ada, run_id, {"approved": True, "decided_by": str(uuid4())})

    assert_problem(response, 422, ErrorCode.VALIDATION_FAILED)
    assert queue == []


@pytest.mark.parametrize("value", [True, "yes", {"approved": "yes"}, {}, {"team_id": "team-1"}])
async def test_an_export_approval_needs_approved_true_or_false_by_name(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queue: list[dict[str, Any]],
    value: Any,
) -> None:
    ada, run_id = await _waiting(client, engine, EXPORT_APPROVAL)
    queue.clear()

    response = await _resume(client, ada, run_id, value)

    assert_problem(response, 422, ErrorCode.VALIDATION_FAILED)
    assert queue == []


@pytest.mark.parametrize("interrupt", [QUESTION, APPROVAL, ADVICE, PHASE_REVIEW])
async def test_an_export_answer_does_not_answer_another_kind_of_interrupt(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    queue: list[dict[str, Any]],
    interrupt: dict[str, Any],
) -> None:
    ada, run_id = await _waiting(client, engine, interrupt)
    queue.clear()

    response = await _resume(client, ada, run_id, {"approved": True})

    assert_problem(response, 422, ErrorCode.VALIDATION_FAILED)
    assert queue == []
