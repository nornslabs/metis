"""Starting a run needs an LLM key that passed its test (``POST /v1/ideas/{id}/runs``).

Same seam as ``test_runs_api``: real app and Postgres as ``metis_app``, the queue replaced by
a recording fake. The refusal is a 402 ``provider.llm_not_ready`` whose ``meta.reason`` says
what is wrong, and it creates no run.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import pytest
from idea_helpers import Caller, create, delete_llm_key, owner
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.core import jobs
from tests.helpers.auth import assert_problem


@pytest.fixture(autouse=True)
def _no_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(jobs, "enqueue", noop)


async def _start(
    client: httpx.AsyncClient, caller: Caller, idea_id: str, key: str | None = None
) -> httpx.Response:
    headers = {**caller.headers, "Idempotency-Key": key or uuid4().hex}
    return await client.post(f"/v1/ideas/{idea_id}/runs", headers=headers)


async def _run_count(engine: AsyncEngine, idea_id: str) -> int:
    async with engine.connect() as conn:
        count = await conn.scalar(
            text("SELECT count(*) FROM ideas.workflow_runs WHERE idea_id = :id"), {"id": idea_id}
        )
    return int(count or 0)


@pytest.mark.parametrize(
    ("tested", "reason"),
    [(None, "not_tested"), (False, "test_failed")],
    ids=["never tested", "last test failed"],
)
async def test_an_llm_key_that_has_not_passed_its_test_cannot_start_a_run(
    client: httpx.AsyncClient, engine: AsyncEngine, tested: bool | None, reason: str
) -> None:
    ada = await owner(client, engine, llm_key_tested=tested)
    idea = await create(client, ada)

    response = await _start(client, ada, idea["id"])

    assert_problem(response, 402, "provider.llm_not_ready")
    assert response.json()["meta"] == {"reason": reason}
    assert await _run_count(engine, idea["id"]) == 0


async def test_a_workspace_without_an_llm_key_cannot_start_a_run(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    await delete_llm_key(engine, ada)
    idea = await create(client, ada)

    response = await _start(client, ada, idea["id"])

    assert_problem(response, 402, "provider.llm_not_ready")
    assert response.json()["meta"] == {"reason": "not_configured"}
    assert await _run_count(engine, idea["id"]) == 0


async def test_an_llm_key_that_passed_its_test_starts_a_run(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)

    response = await _start(client, ada, idea["id"])

    assert response.status_code == 202, response.text
    assert await _run_count(engine, idea["id"]) == 1


async def test_a_repeated_start_still_returns_its_run_after_the_key_is_removed(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    idea = await create(client, ada)
    key = uuid4().hex
    first = await _start(client, ada, idea["id"], key)
    await delete_llm_key(engine, ada)

    again = await _start(client, ada, idea["id"], key)

    assert again.status_code == 202
    assert again.json() == first.json()


async def test_an_unknown_idea_is_still_404_without_an_llm_key(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    ada = await owner(client, engine)
    await delete_llm_key(engine, ada)

    response = await _start(client, ada, str(uuid4()))

    assert_problem(response, 404, "idea.not_found")
