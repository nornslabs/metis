"""Runs the real Scorer on one case: seed, ``run_graph``, read the stored score, clean up.

The Scorer node and its tools are the production ones. Every other specialist is a stub (the
run starts at ``scoring``), no Exa key is saved (so the Scorer runs without a search tool) and
the stored score is read back through the ``scoring`` module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from evals.cases import Case
from evals.checks import check_run
from evals.report import RunOutcome, Usage
from evals.seed import LlmConfig, Seeded, remove_case, seed_case, usage_of
from metis.agent.runner import RunnerDeps
from metis.agent.specialists.stubs import SpecialistNode, stub_specialists
from metis.agent.supervisor import Specialist
from metis.core.db import set_workspace
from metis.jobs.run_graph import run_graph
from metis.modules import scoring
from metis.modules.scoring import ScoreRun

ModelClient = Callable[[], httpx.AsyncClient]


@dataclass(frozen=True)
class Harness:
    """What every case run shares."""

    owner: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    app_database_url: str
    redis: Redis
    llm: LlmConfig
    model_client: ModelClient | None = None


@dataclass(frozen=True)
class CaseRun:
    """The score one run stored (``None`` when it stored none), what it cost, how it was judged."""

    score: ScoreRun | None
    outcome: RunOutcome
    usage: Usage


async def run_case_once(harness: Harness, case: Case) -> CaseRun:
    """One Scorer run of ``case`` in a throwaway workspace, removed afterwards."""
    seeded = await seed_case(harness.owner, case, harness.llm)
    try:
        await run_graph(
            {"redis": harness.redis, "run_deps": _deps(harness)},
            run_id=str(seeded.run_id),
            workspace_id=str(seeded.workspace_id),
        )
        score = await _stored_score(harness, seeded)
        error_code = None if score is not None else await _error_code(harness.owner, seeded)
        usage = await usage_of(harness.owner, seeded)
    finally:
        await remove_case(harness.owner, seeded)
    failures = check_run(case, score) if score is not None else ()
    outcome = RunOutcome(
        band=score.band if score else None,
        total=score.total if score else None,
        failures=failures,
        error_code=error_code,
    )
    return CaseRun(score, outcome, usage)


def _deps(harness: Harness) -> RunnerDeps:
    stubs: dict[Specialist, SpecialistNode] = {
        s: node for s, node in stub_specialists().items() if s is not Specialist.SCORER
    }
    return RunnerDeps(
        sessions=harness.sessions,
        database_url=harness.app_database_url,
        specialists=stubs,
        llm_http_client=harness.model_client,
    )


async def _stored_score(harness: Harness, seeded: Seeded) -> ScoreRun | None:
    async with harness.sessions() as session:
        await set_workspace(session, seeded.workspace_id)
        latest = await scoring.latest_score(session, seeded.workspace_id, seeded.idea_id)
    return latest if latest is not None and latest.run_id == seeded.run_id else None


async def _error_code(owner: AsyncEngine, seeded: Seeded) -> str:
    async with owner.connect() as conn:
        code = await conn.scalar(
            text("SELECT error->>'code' FROM ideas.workflow_runs WHERE id = :id"),
            {"id": seeded.run_id},
        )
    return str(code) if code else "unknown"
