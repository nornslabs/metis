"""The Researcher through the ``run_graph`` job, from ``researching`` to ``scoring``.

Seam: the job function, called as Arq would (an answer is a second call with ``resume``), on
real Postgres as ``metis_app``, real Redis and the real checkpointer. Two fakes sit at the
HTTP boundary: a scripted OpenAI-compatible LLM and an in-process Exa MCP server. Tests check
what the user and the database see: the closed snapshot, its items and linked competitors,
the KB, questions asked, events, run status.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from metis.agent.tools.exa import ExaCallBudget
from metis.core.events import RunEventType
from metis.helpers.ids import uuid7
from metis.modules import auth, identity
from metis.modules.identity import MemberRole, Membership, ProviderKind
from metis.modules.identity.service.provider_keys import set_key
from tests.agent.interview_helpers import Call, Reply, ScriptedLLM
from tests.agent.run_job_helpers import (
    QueuedRun,
    events_of,
    idea_stage,
    job_ctx,
    keyed_run,
    node_events,
    run_job,
    run_row,
    statuses,
)
from tests.modules.identity.fake_exa_mcp import FakeExaMcp

ACME = {
    "name": "Acme CRM",
    "url": "https://acme.example.com/pricing",
    "description": "A CRM for freelancers.",
    "overlap": 0.8,
}
FACT = {
    "kind": "market_fact",
    "title": "Freelancer market size",
    "url": "https://stats.example.com/freelancers",
    "quote": "There are 60 million freelancers.",
    "claim": "The market has 60 million freelancers.",
    "confidence": 0.7,
}
Q_COUNTRY = "Which country do you start in?"
Q_PRICE = "Is a monthly price acceptable?"


def call(tool: str, /, **args: Any) -> Reply:
    return Reply(calls=(Call(tool, args),))


def search(query: str) -> Reply:
    return call("web_search_exa", query=query, objective="find competitors")


def finish(summary: str = "Acme CRM is the main competitor.", **extra: Any) -> Reply:
    return call("finish_research", summary=summary, **extra)


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM()


@pytest_asyncio.fixture
async def exa() -> AsyncIterator[FakeExaMcp]:
    async with FakeExaMcp().running() as fake:
        yield fake


@pytest.fixture
def ctx(
    redis: Redis,
    app_sessions: async_sessionmaker[AsyncSession],
    checkpointer: AsyncPostgresSaver,
    llm: ScriptedLLM,
    exa: FakeExaMcp,
) -> dict[str, Any]:
    def make_client(headers: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=exa.transport(), headers=dict(headers))

    return job_ctx(redis, app_sessions, llm=llm, exa=make_client)


async def _researching_run(engine: AsyncEngine, *, exa_key: bool = True) -> QueuedRun:
    run = await keyed_run(engine, stage="researching")
    if exa_key:
        await _save_exa_key(engine, run.workspace_id)
    return run


async def _new_run_on_same_idea(engine: AsyncEngine, run: QueuedRun) -> QueuedRun:
    """A new queued run on ``run``'s idea (the first one has finished)."""
    new_id = uuid7()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ideas.workflow_runs (id, workspace_id, idea_id) "
                "SELECT :new, workspace_id, idea_id FROM ideas.workflow_runs WHERE id = :old"
            ),
            {"new": new_id, "old": run.run_id},
        )
    return QueuedRun(new_id, run.workspace_id)


async def _save_exa_key(engine: AsyncEngine, workspace_id: UUID) -> None:
    async with engine.connect() as conn:
        owner_id = await conn.scalar(
            text("SELECT created_by FROM identity.workspaces WHERE id = :ws"), {"ws": workspace_id}
        )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = await auth.get_user(session, owner_id)
        assert user is not None
        workspace = await identity.ensure_personal_workspace(session, user)
        owner = Membership(workspace=workspace, role=MemberRole.OWNER)
        await set_key(session, owner, ProviderKind.EXA, "exa-test-key")
        await session.commit()


async def _rows(engine: AsyncEngine, sql: str, run: QueuedRun) -> list[tuple[Any, ...]]:
    async with engine.connect() as conn:
        result = await conn.execute(text(sql), {"run": run.run_id})
        return [tuple(row) for row in result.all()]


async def _snapshots(engine: AsyncEngine, run: QueuedRun) -> list[tuple[Any, ...]]:
    """``(summary, closed)`` of the run's snapshots."""
    return await _rows(
        engine,
        "SELECT summary, closed_at IS NOT NULL FROM research.snapshots WHERE run_id = :run",
        run,
    )


async def _items(engine: AsyncEngine, run: QueuedRun) -> list[tuple[Any, ...]]:
    return await _rows(
        engine,
        "SELECT i.kind, i.title, i.url, i.quote FROM research.items i "
        "JOIN research.snapshots s ON s.id = i.snapshot_id WHERE s.run_id = :run ORDER BY i.id",
        run,
    )


async def _linked(engine: AsyncEngine, run: QueuedRun) -> list[tuple[Any, ...]]:
    """``(name, domain, overlap)`` of the competitors linked to the run's snapshot."""
    return await _rows(
        engine,
        "SELECT c.name, c.domain, ic.overlap FROM research.idea_competitors ic "
        "JOIN research.competitors c ON c.id = ic.competitor_id "
        "JOIN research.snapshots s ON s.id = ic.snapshot_id WHERE s.run_id = :run",
        run,
    )


async def _kb(engine: AsyncEngine, run: QueuedRun) -> list[tuple[Any, ...]]:
    """``(domain, has_embedding)`` of the workspace's KB."""
    return await _rows(
        engine,
        "SELECT domain, embedding IS NOT NULL FROM research.competitors "
        "WHERE workspace_id = (SELECT workspace_id FROM ideas.workflow_runs WHERE id = :run)",
        run,
    )


async def _clarification_turns(engine: AsyncEngine, run: QueuedRun) -> list[tuple[Any, ...]]:
    return await _rows(
        engine,
        "SELECT topic, source, question, answer FROM ideas.interview_turns "
        "WHERE run_id = :run ORDER BY id",
        run,
    )


async def test_research_saves_sourced_findings_and_hands_over_to_scoring(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any], llm: ScriptedLLM, exa: FakeExaMcp
) -> None:
    run = await _researching_run(engine)
    llm.add(call("kb_lookup", query="crm for freelancers"), search("freelancer crm tools"))
    llm.add(call("web_fetch_exa", url="https://acme.example.com"))
    llm.add(call("kb_upsert_competitor", **ACME), call("save_research_item", **FACT))
    llm.add(finish())

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "succeeded"
    assert await _snapshots(engine, run) == [("Acme CRM is the main competitor.", True)]
    assert await _linked(engine, run) == [("Acme CRM", "acme.example.com", Decimal("0.80"))]
    assert await _items(engine, run) == [("market_fact", FACT["title"], FACT["url"], FACT["quote"])]
    assert [c["query"] for c in exa.tool_calls] == ["freelancer crm tools"]
    events = await events_of(redis, run)
    exa_calls = [
        e.data for e in events if e.type is RunEventType.TOOL_CALL and "result_count" in e.data
    ]
    assert [c["query"] for c in exa_calls] == ["freelancer crm tools", "https://acme.example.com"]
    assert set(exa.api_keys) == {"exa-test-key"}
    assert await idea_stage(engine, run) == "exported"  # the stubs after the Researcher finish


async def test_an_item_without_a_source_url_is_refused_and_research_goes_on(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _researching_run(engine)
    no_url = {k: v for k, v in FACT.items() if k != "url"}
    llm.add(call("save_research_item", **no_url))
    llm.add(finish())

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "succeeded"
    assert await _items(engine, run) == []
    assert "not saved" in llm.shown(1)  # the model was told why


async def test_a_competitor_or_market_fact_needs_a_supporting_quote(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _researching_run(engine)
    no_quote = {k: v for k, v in FACT.items() if k != "quote"}
    llm.add(call("save_research_item", **no_quote))
    llm.add(finish())

    await run_job(ctx, run)

    assert await _items(engine, run) == []
    assert "needs a quote" in llm.shown(1)


async def test_a_rerun_after_the_snapshot_closed_does_not_research_again(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _researching_run(engine)
    llm.add(call("kb_upsert_competitor", **ACME))
    llm.add(finish("Acme is the main competitor."))
    await run_job(ctx, run)
    calls_before = llm.calls
    # The worker died after the snapshot closed but before the checkpoint: the snapshot is
    # closed, the run is still ``running`` and its graph restarts from the idea's stage.
    async with engine.begin() as conn:
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            await conn.execute(
                text(f"DELETE FROM agent.{table} WHERE thread_id = :id"), {"id": str(run.run_id)}
            )
        await conn.execute(
            text("UPDATE ideas.workflow_runs SET status = 'running' WHERE id = :id"),
            {"id": run.run_id},
        )

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "succeeded"
    assert llm.calls == calls_before  # no new model call
    assert await _snapshots(engine, run) == [("Acme is the main competitor.", True)]


async def test_a_snapshot_with_no_competitor_says_so(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _researching_run(engine)
    llm.add(finish("Nothing close to this exists.", no_direct_competitors=True))

    await run_job(ctx, run)

    [(summary, closed)] = await _snapshots(engine, run)
    assert closed
    assert summary == "Nothing close to this exists. No direct competitors found."


async def test_the_same_competitor_is_one_kb_row_and_gets_an_embedding(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _researching_run(engine)
    llm.embeddings = True
    other_page = {**ACME, "url": "https://www.acme.example.com/about", "overlap": 0.6}
    llm.add(call("kb_lookup", query="acme crm"), call("kb_upsert_competitor", **ACME))
    llm.add(call("kb_upsert_competitor", **other_page))
    llm.add(finish())

    await run_job(ctx, run)

    assert await _kb(engine, run) == [("acme.example.com", True)]
    assert await _linked(engine, run) == [("Acme CRM", "acme.example.com", Decimal("0.60"))]
    assert llm.embedding_inputs  # the lookup and the upserts were embedded


async def test_clarification_goes_through_the_interview_once_then_research_resumes(
    engine: AsyncEngine, redis: Redis, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _researching_run(engine)
    llm.add(call("kb_upsert_competitor", **ACME))
    llm.add(finish("Draft.", needs_clarification=[Q_COUNTRY, Q_PRICE]))
    llm.add(call("save_research_item", **FACT), finish("Final summary."))

    await run_job(ctx, run)
    first = await run_row(engine, run)
    await run_job(ctx, run, resume="Germany")
    second = await run_row(engine, run)
    assert [closed for _, closed in await _snapshots(engine, run)] == [False]  # still open
    await run_job(ctx, run, resume="Yes")
    last = await run_row(engine, run)

    assert first.pending_interrupt == {"type": "question", "question": Q_COUNTRY}
    assert second.pending_interrupt == {"type": "question", "question": Q_PRICE}
    assert last.status == "succeeded"
    assert await _clarification_turns(engine, run) == [
        ("other", "asked", Q_COUNTRY, "Germany"),
        ("other", "asked", Q_PRICE, "Yes"),
    ]
    assert "Germany" in llm.shown(2)  # the second pass saw the answers
    assert await _snapshots(engine, run) == [("Final summary.", True)]
    assert len(await _linked(engine, run)) == 1 and len(await _items(engine, run)) == 1
    questions = [
        e.data["question"] for e in await events_of(redis, run) if e.type is RunEventType.INTERRUPT
    ]
    assert questions == [Q_COUNTRY, Q_PRICE]


async def test_a_second_clarification_request_is_ignored(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _researching_run(engine)
    llm.add(finish("Draft.", needs_clarification=[Q_COUNTRY]))
    llm.add(finish("Done.", needs_clarification=[Q_PRICE]))

    await run_job(ctx, run)
    await run_job(ctx, run, resume="Germany")

    assert (await run_row(engine, run)).status == "succeeded"
    assert await _snapshots(engine, run) == [("Done. No direct competitors found.", True)]
    assert [t[2] for t in await _clarification_turns(engine, run)] == [Q_COUNTRY]


async def test_the_exa_call_cap_stops_a_researcher_that_keeps_searching(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM, exa: FakeExaMcp
) -> None:
    run = await _researching_run(engine)
    for n in range(15):
        llm.add(search(f"query {n}"))
    llm.add(finish())

    await run_job(ctx, run)

    assert (await run_row(engine, run)).status == "succeeded"
    assert len(exa.tool_calls) == 12
    assert "limit" in llm.shown(13)  # the 13th call was answered with the limit message


async def test_the_exa_cap_is_per_run_not_per_pass_or_rerun(redis: Redis) -> None:
    run_id = uuid7()
    first, second = (ExaCallBudget(redis, run_id, 12) for _ in range(2))

    taken = [await first.take() for _ in range(8)] + [await second.take() for _ in range(8)]

    assert taken == [True] * 12 + [False] * 4


async def test_a_workspace_without_an_exa_key_skips_research_and_the_run_succeeds(
    engine: AsyncEngine,
    redis: Redis,
    ctx: dict[str, Any],
    llm: ScriptedLLM,
    exa: FakeExaMcp,
) -> None:
    run = await _researching_run(engine, exa_key=False)

    await run_job(ctx, run)

    events = await events_of(redis, run)
    notices = [e.data for e in events if e.type is RunEventType.NOTICE]
    assert (await run_row(engine, run)).status == "succeeded"
    assert notices == [
        {"code": "research.skipped_no_exa", "text": "Research is skipped: Exa isn't set up."}
    ]
    assert node_events(events) == [("node_started", "researcher"), ("node_finished", "researcher")]
    assert statuses(events) == ["running", "succeeded"]
    assert (llm.calls, exa.api_keys, exa.tool_calls) == (0, [], [])
    assert await _snapshots(engine, run) == []
    assert await idea_stage(engine, run) == "researching"


async def test_a_later_run_with_an_exa_key_does_the_research(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    skipped = await _researching_run(engine, exa_key=False)
    await run_job(ctx, skipped)
    await _save_exa_key(engine, skipped.workspace_id)
    later = await _new_run_on_same_idea(engine, skipped)
    llm.add(finish())

    await run_job(ctx, later)

    assert (await run_row(engine, later)).status == "succeeded"
    [(summary, closed)] = await _snapshots(engine, later)
    assert closed and summary.startswith("Acme CRM is the main competitor.")
    assert await idea_stage(engine, later) == "exported"  # the stubs after the Researcher finish


async def test_a_loop_that_never_settles_fails_with_the_step_limit(
    engine: AsyncEngine, ctx: dict[str, Any], llm: ScriptedLLM
) -> None:
    run = await _researching_run(engine)
    for _ in range(60):
        llm.add(call("kb_lookup", query="crm for freelancers"))

    await run_job(ctx, run)

    row = await run_row(engine, run)
    assert row.status == "failed"
    assert row.error is not None and row.error["code"] == "run.step_limit_reached"
    assert await _snapshots(engine, run) == [(None, False)]  # opened, never closed
