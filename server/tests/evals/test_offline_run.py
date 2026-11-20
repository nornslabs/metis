"""The harness end to end, offline: the committed cases scored from ``recorded.jsonl``.

Seam: the ``run_graph`` job on real Postgres as ``metis_app`` and real Redis (as in
``tests/agent/test_scorer.py``), driven by the eval harness with a replayed model instead of a
real one. The recording holds a few deliberately bad answers, so the test checks what a developer
sees: which cases fail and why, the rates, the variance flags, and that nothing is left behind.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from evals.cases import Case, load_cases
from evals.harness import Harness
from evals.recorded_llm import RecordedLLM, load_recordings
from evals.report import CaseOutcome, format_report, pass_rate
from evals.run_scoring import PLACEHOLDER_LLM, _evaluate
from metis.agent.checkpoint import setup_checkpointer
from tests.agent.graph_helpers import APP_DATABASE_URL
from tests.modules.conftest import app_sessions, engine, redis  # noqa: F401  (shared fixtures)

FAILING = {
    "habit-pets": "band build, expected promising",
    "recipe-cost-calc": "no score stored (score.invalid_submission)",
    "pet-vaccine-reminders": "problem_severity 7 outside 3-5",
}
UNSTABLE = {"habit-pets", "meeting-notes-sales", "pet-vaccine-reminders"}


@pytest.fixture
def cases() -> tuple[Case, ...]:
    return load_cases()


@pytest.fixture
async def harness(
    engine: AsyncEngine,  # noqa: F811
    redis: Redis,  # noqa: F811
    app_sessions: async_sessionmaker[AsyncSession],  # noqa: F811
    cases: tuple[Case, ...],
) -> Harness:
    await setup_checkpointer(APP_DATABASE_URL)
    replay = RecordedLLM(load_recordings(), {c.title: c.id for c in cases})
    return Harness(engine, app_sessions, APP_DATABASE_URL, redis, PLACEHOLDER_LLM, replay.client)


def _report(outcomes: Sequence[CaseOutcome]) -> str:
    return format_report(outcomes, model="recorded replay", prompt="scorer.v2.md", usage=None)


async def test_the_recorded_bad_answers_are_the_cases_that_fail(
    harness: Harness, cases: tuple[Case, ...]
) -> None:
    outcomes, _ = await _evaluate(harness, cases, repeat=2)

    failing = {o.case_id for o in outcomes if not o.passed}
    assert failing == set(FAILING)
    report = _report(outcomes)
    for case_id, reason in FAILING.items():
        assert f"{case_id}: " in report
        assert reason in report


async def test_the_rates_follow_from_the_failures(
    harness: Harness, cases: tuple[Case, ...]
) -> None:
    outcomes, _ = await _evaluate(harness, cases, repeat=2)

    assert pass_rate(outcomes) == (len(cases) - len(FAILING)) / len(cases)
    assert "Pass rate: 11/14 = 79%" in _report(outcomes)


async def test_a_mark_that_moves_two_points_between_runs_is_flagged_unstable(
    harness: Harness, cases: tuple[Case, ...]
) -> None:
    outcomes, _ = await _evaluate(harness, cases, repeat=2)

    assert {o.case_id for o in outcomes if o.flags} == UNSTABLE
    flagged = next(o for o in outcomes if o.case_id == "meeting-notes-sales")
    assert flagged.passed
    assert flagged.flags == ("timing unstable (7-9)",)


async def test_a_run_that_fails_does_not_stop_the_next_case(
    harness: Harness, cases: tuple[Case, ...]
) -> None:
    outcomes, _ = await _evaluate(harness, cases, repeat=1)

    assert [o.case_id for o in outcomes] == [c.id for c in cases]
    failed = next(o for o in outcomes if o.case_id == "recipe-cost-calc")
    assert failed.runs[0].error_code == "score.invalid_submission"
    assert failed.runs[0].band is None


async def test_the_throwaway_workspaces_are_gone_after_the_run(
    harness: Harness,
    cases: tuple[Case, ...],
    engine: AsyncEngine,  # noqa: F811
) -> None:
    await _evaluate(harness, cases[:3], repeat=2)

    async with engine.connect() as conn:
        left = [
            await conn.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in (
                "identity.workspaces",
                "ideas.ideas",
                "scoring.score_runs",
                "auth.users",
                "core.outbox",
            )
        ]
    assert left == [0, 0, 0, 0, 0]


async def test_the_run_records_the_tokens_the_model_used(
    harness: Harness, cases: tuple[Case, ...]
) -> None:
    _, usage = await _evaluate(harness, cases[:1], repeat=2)

    assert usage.input_tokens > 0
    assert usage.output_tokens > 0
