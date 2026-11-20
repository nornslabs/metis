"""Shared setup for the Scorer and Advisor job tests: scripted replies, a research snapshot,
a saved Exa key and readers of the stored scores."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from metis.helpers.ids import uuid7
from metis.modules import auth, identity
from metis.modules.identity import MemberRole, Membership, ProviderKind
from metis.modules.identity.service.provider_keys import set_key
from tests.agent.interview_helpers import Call, Reply, ScriptedLLM
from tests.agent.run_job_helpers import QueuedRun, keyed_run, node_events

REPORT = "https://stats.example.com/freelancers"
RIVAL = "https://acme.example.com/pricing"
SEARCHED = "https://example.com"  # what the fake Exa server returns for every search
WEIGHTED_55 = {
    "problem_severity": 6,
    "uniqueness": 6,
    "market_demand": 5,
    "value": 5,
    "feasibility": 5,
    "timing": 5,
}
WEIGHTED_54 = {**WEIGHTED_55, "timing": 4}
SPEC_PATH = ["scorer", "architect", "planner", "integrator"]
ADVISED_PATH = ["scorer", "advisor", "scorer", "architect", "planner", "integrator"]


def entry(param: str, raw: int, url: str | None = REPORT) -> dict[str, Any]:
    if url is None:
        return {
            "param": param,
            "raw": raw,
            "reason": f"No source for {param}.",
            "confidence": 0.2,
            "evidence": [],
            "no_evidence": True,
        }
    return {
        "param": param,
        "raw": raw,
        "reason": f"Why {param} is {raw}.",
        "confidence": 0.7,
        "evidence": [{"url": url, "title": "Source", "quote": "A supporting sentence."}],
        "no_evidence": False,
    }


def submit(marks: dict[str, int] | None = None, url: str | None = REPORT) -> Reply:
    chosen = marks or {name: 7 for name in WEIGHTED_55}
    params = [entry(name, raw, url) for name, raw in chosen.items()]
    return Reply(calls=(Call("submit_scores", {"params": params}),))


def call(tool: str, /, **args: Any) -> Reply:
    return Reply(calls=(Call(tool, args),))


def search(query: str) -> Reply:
    return call("web_search_exa", query=query, objective="check the market")


async def scoring_run(
    engine: AsyncEngine, *, exa_key: bool = True, snapshot: bool = True
) -> QueuedRun:
    run = await keyed_run(engine, stage="scoring")
    if exa_key:
        await save_exa_key(engine, run.workspace_id)
    if snapshot:
        await save_snapshot(engine, run)
    return run


async def save_snapshot(engine: AsyncEngine, run: QueuedRun) -> None:
    """A closed research snapshot with one sourced market fact, as the Researcher leaves it."""
    snapshot_id = uuid7()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO research.snapshots (id, workspace_id, idea_id, run_id, summary, "
                "closed_at) SELECT :id, workspace_id, idea_id, id, 'Acme is the main rival.', "
                "now() FROM ideas.workflow_runs WHERE id = :run"
            ),
            {"id": snapshot_id, "run": run.run_id},
        )
        await conn.execute(
            text(
                "INSERT INTO research.items (id, workspace_id, snapshot_id, kind, title, url, "
                "quote, claim, confidence) VALUES (:id, :ws, :snap, 'market_fact', 'Market size', "
                ":url, 'There are 60 million freelancers.', 'The market is large.', 0.7)"
            ),
            {"id": uuid7(), "ws": run.workspace_id, "snap": snapshot_id, "url": REPORT},
        )
        competitor_id = uuid7()
        await conn.execute(
            text(
                "INSERT INTO research.competitors (id, workspace_id, name, url, domain, pricing) "
                "VALUES (:id, :ws, 'Acme CRM', :url, 'acme.example.com', '$10 a month')"
            ),
            {"id": competitor_id, "ws": run.workspace_id, "url": RIVAL},
        )
        await conn.execute(
            text(
                "INSERT INTO research.idea_competitors (snapshot_id, competitor_id, workspace_id, "
                "idea_id, overlap) SELECT :snap, :comp, workspace_id, idea_id, 0.8 "
                "FROM ideas.workflow_runs WHERE id = :run"
            ),
            {"snap": snapshot_id, "comp": competitor_id, "run": run.run_id},
        )


async def save_exa_key(engine: AsyncEngine, workspace_id: UUID) -> None:
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
    async with engine.begin() as conn:  # the key passed its test, so the Scorer may use it
        await conn.execute(
            text(
                "UPDATE identity.provider_keys SET last_test_ok = true "
                "WHERE workspace_id = :ws AND kind = 'exa'"
            ),
            {"ws": workspace_id},
        )


async def score_runs(engine: AsyncEngine, run: QueuedRun) -> list[tuple[Any, ...]]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT total, band, trigger FROM scoring.score_runs WHERE run_id = :run"),
            {"run": run.run_id},
        )
        return [tuple(row) for row in result.all()]


async def score_params(engine: AsyncEngine, run: QueuedRun) -> list[tuple[Any, ...]]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT p.param, p.raw, p.no_evidence, jsonb_array_length(p.evidence) "
                "FROM scoring.score_params p JOIN scoring.score_runs r ON r.id = p.score_run_id "
                "WHERE r.run_id = :run ORDER BY p.param"
            ),
            {"run": run.run_id},
        )
        return [tuple(row) for row in result.all()]


async def current_score(engine: AsyncEngine, run: QueuedRun) -> int | None:
    async with engine.connect() as conn:
        return await conn.scalar(
            text(
                "SELECT current_score FROM ideas.ideas "
                "WHERE id = (SELECT idea_id FROM ideas.workflow_runs WHERE id = :id)"
            ),
            {"id": run.run_id},
        )


def tool_names(llm: ScriptedLLM) -> set[str]:
    """The tools the model was offered in its first call."""
    return {tool["function"]["name"] for tool in llm.bodies[0]["tools"]}


def finished(events: list[Any]) -> list[str]:
    return [node for kind, node in node_events(events) if kind == "node_finished"]
