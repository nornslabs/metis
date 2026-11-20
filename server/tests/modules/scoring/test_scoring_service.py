"""Score runs at the scoring module's public seam.

Runs as ``metis_app`` (RLS on) against a migrated Postgres. The Scorer (SHIP-240) calls these
functions; the HTTP routes are covered in ``test_scoring_api.py``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from metis.core.errors import (
    IdeaNotFoundError,
    InvalidInputError,
    RunNotFoundError,
    ScoreRunNotFoundError,
)
from metis.modules import ideas, scoring
from metis.modules.scoring import ScoreBand, ScoreParam, ScoreRun, ScoreTrigger
from tests.modules.research.research_helpers import Run, another_run, archive, new_run
from tests.modules.scoring.scoring_helpers import (
    Sessions,
    in_workspace,
    marks,
    outbox_events,
    param,
)

P = ScoreParam


async def _record(
    sessions: Sessions,
    run: Run,
    params: list[scoring.NewParamScore] | None = None,
    trigger: ScoreTrigger = ScoreTrigger.MANUAL,
) -> ScoreRun:
    async with in_workspace(sessions, run.workspace_id) as session:
        return await scoring.record_score(
            session,
            run.workspace_id,
            run.idea_id,
            run.run_id,
            marks() if params is None else params,
            trigger,
        )


async def test_the_total_is_the_sum_of_weighted_marks(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    raws = {
        P.PROBLEM_SEVERITY: 8,  # 20.00
        P.UNIQUENESS: 6,  # 15.00
        P.MARKET_DEMAND: 7,  # 10.50
        P.VALUE: 9,  # 13.50
        P.FEASIBILITY: 4,  # 4.00
        P.TIMING: 5,  # 5.00  -> 68.00
    }

    score = await _record(app_sessions, run, marks(raws))

    assert (score.total, score.band, score.rubric_version) == (68, ScoreBand.PROMISING, 1)
    assert [(p.param, p.weight, p.raw, p.weighted) for p in score.params] == [
        (P.PROBLEM_SEVERITY, 25, 8, 20.0),
        (P.UNIQUENESS, 25, 6, 15.0),
        (P.MARKET_DEMAND, 15, 7, 10.5),
        (P.VALUE, 15, 9, 13.5),
        (P.FEASIBILITY, 10, 4, 4.0),
        (P.TIMING, 10, 5, 5.0),
    ]


def _marks(a: int, b: int, c: int, d: int, e: int, f: int) -> list[scoring.NewParamScore]:
    return marks(dict(zip(ScoreParam, (a, b, c, d, e, f), strict=True)))


@pytest.mark.parametrize(
    ("raws", "total", "band"),
    [
        ((10, 10, 5, 5, 5, 5), 75, ScoreBand.BUILD),
        ((10, 10, 5, 5, 5, 4), 74, ScoreBand.PROMISING),
        ((10, 10, 0, 0, 3, 2), 55, ScoreBand.PROMISING),
        ((10, 10, 0, 0, 3, 1), 54, ScoreBand.ADVISE),
        ((10, 9, 0, 0, 4, 3), 55, ScoreBand.PROMISING),  # 54.5 rounds half up
        ((10, 10, 10, 10, 10, 10), 100, ScoreBand.BUILD),
        ((0, 0, 0, 0, 0, 0), 0, ScoreBand.ADVISE),
    ],
)
async def test_band_edges_and_rounding(
    engine: AsyncEngine,
    app_sessions: Sessions,
    raws: tuple[int, int, int, int, int, int],
    total: int,
    band: ScoreBand,
) -> None:
    run = await new_run(engine)

    score = await _record(app_sessions, run, _marks(*raws))

    assert (score.total, score.band) == (total, band)


async def test_params_come_back_in_rubric_order_whatever_the_submission_order(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)

    score = await _record(app_sessions, run, list(reversed(marks())))

    assert [p.param for p in score.params] == list(ScoreParam)
    assert score.weights == {
        P.PROBLEM_SEVERITY: 25,
        P.UNIQUENESS: 25,
        P.MARKET_DEMAND: 15,
        P.VALUE: 15,
        P.FEASIBILITY: 10,
        P.TIMING: 10,
    }


async def test_the_rubric_has_six_weights_summing_to_100(
    app_sessions: Sessions, engine: AsyncEngine
) -> None:
    run = await new_run(engine)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        rubric = await scoring.get_rubric(session)

    assert rubric.version == 1
    assert set(rubric.weights) == set(ScoreParam)
    assert sum(rubric.weights.values()) == 100


async def test_reason_confidence_and_evidence_are_stored(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    given = [
        param(P.PROBLEM_SEVERITY, reason="Freelancers lose invoices.", confidence=0.85),
        *(param(name) for name in list(ScoreParam)[1:5]),
        param(P.TIMING, evidence=[], no_evidence=True, confidence=0.2),
    ]

    score = await _record(app_sessions, run, given)

    severity, *_, timing = score.params
    assert (severity.reason, severity.confidence, severity.no_evidence) == (
        "Freelancers lose invoices.",
        0.85,
        False,
    )
    assert [(e.url, e.title, e.quote) for e in severity.evidence] == [
        ("https://example.com/report", "Report", "A quote.")
    ]
    assert (timing.no_evidence, timing.evidence, timing.confidence) == (True, (), 0.2)


async def test_a_missing_parameter_is_refused_and_nothing_is_stored(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)

    with pytest.raises(InvalidInputError, match="Invalid input"):
        await _record(app_sessions, run, marks()[:5])

    assert await _score_count(engine, run) == 0


async def test_a_duplicate_parameter_is_refused(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)

    with pytest.raises(InvalidInputError):
        await _record(app_sessions, run, [*marks()[:5], param(P.PROBLEM_SEVERITY)])


@pytest.mark.parametrize(
    "fields",
    [
        {"raw": 11},
        {"raw": -1},
        {"confidence": 1.1},
        {"reason": "  "},
        {"evidence": [{"url": "ftp://example.com", "title": "T", "quote": ""}]},
        {"evidence": [{"url": "https://example.com", "title": "", "quote": ""}]},
    ],
)
def test_a_bad_mark_is_refused_with_a_422(fields: dict[str, object]) -> None:
    with pytest.raises(InvalidInputError):
        param(P.VALUE, **fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"evidence": []},  # no sources and no flag
        {"evidence": [], "no_evidence": True, "confidence": 0.31},  # too sure for a guess
    ],
)
async def test_a_parameter_without_evidence_needs_the_flag_and_a_low_confidence(
    engine: AsyncEngine, app_sessions: Sessions, fields: dict[str, object]
) -> None:
    run = await new_run(engine)

    with pytest.raises(InvalidInputError):
        await _record(app_sessions, run, [*marks()[:5], param(P.TIMING, **fields)])


async def test_the_flag_with_evidence_is_refused(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)

    with pytest.raises(InvalidInputError):
        await _record(app_sessions, run, [*marks()[:5], param(P.TIMING, no_evidence=True)])


async def test_no_evidence_is_accepted_at_the_confidence_cap(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)

    score = await _record(
        app_sessions,
        run,
        [*marks()[:5], param(P.TIMING, evidence=[], no_evidence=True, confidence=0.3)],
    )

    assert score.params[-1].confidence == 0.3


async def test_an_unknown_or_archived_idea_is_not_found(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    await archive(engine, run.idea_id)

    with pytest.raises(IdeaNotFoundError):
        await _record(app_sessions, run)


async def test_a_run_of_another_idea_is_refused(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    other = await another_run(engine, run.workspace_id)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        with pytest.raises(RunNotFoundError):
            await scoring.record_score(
                session, run.workspace_id, run.idea_id, other.run_id, marks(), ScoreTrigger.MANUAL
            )


async def test_recording_sets_the_current_score_without_touching_the_version(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    async with in_workspace(app_sessions, run.workspace_id) as session:
        before = await ideas.get_idea(session, run.workspace_id, run.idea_id)

    await _record(app_sessions, run, _marks(10, 10, 5, 5, 5, 5))
    await _record(app_sessions, run, _marks(10, 10, 0, 0, 3, 1))

    async with in_workspace(app_sessions, run.workspace_id) as session:
        after = await ideas.get_idea(session, run.workspace_id, run.idea_id)
    assert (before.current_score, after.current_score) == (None, 54)
    assert (after.version, after.stage) == (before.version, before.stage)


async def test_recording_writes_score_computed_with_the_previous_total(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)

    first = await _record(app_sessions, run, _marks(10, 10, 5, 5, 5, 5), ScoreTrigger.MANUAL)
    second = await _record(app_sessions, run, _marks(10, 10, 0, 0, 3, 1), ScoreTrigger.SIGNAL)

    events = await outbox_events(engine, run.workspace_id)
    assert events == [
        {
            "idea_id": str(run.idea_id),
            "score_run_id": str(first.id),
            "run_id": str(run.run_id),
            "total": 75,
            "band": "build",
            "trigger": "manual",
            "previous_total": None,
        },
        {
            "idea_id": str(run.idea_id),
            "score_run_id": str(second.id),
            "run_id": str(run.run_id),
            "total": 54,
            "band": "advise",
            "trigger": "signal",
            "previous_total": 75,
        },
    ]


async def test_a_refused_score_leaves_no_event_and_no_current_score(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)

    with pytest.raises(InvalidInputError):
        await _record(app_sessions, run, marks()[:5])

    assert await outbox_events(engine, run.workspace_id) == []


async def test_history_is_newest_first_and_latest_is_the_newest(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    first = await _record(app_sessions, run, _marks(0, 0, 0, 0, 0, 0))
    second = await _record(app_sessions, run, _marks(5, 5, 5, 5, 5, 5))
    third = await _record(app_sessions, run, _marks(10, 10, 10, 10, 10, 10))

    async with in_workspace(app_sessions, run.workspace_id) as session:
        history = await scoring.score_history(session, run.workspace_id, run.idea_id)
        latest = await scoring.latest_score(session, run.workspace_id, run.idea_id)

    assert [s.id for s in history.items] == [third.id, second.id, first.id]
    assert [s.total for s in history.items] == [100, 50, 0]
    assert latest is not None and latest.id == third.id and len(latest.params) == 6


async def test_latest_is_none_before_the_first_score_and_history_is_empty(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        assert await scoring.latest_score(session, run.workspace_id, run.idea_id) is None
        history = await scoring.score_history(session, run.workspace_id, run.idea_id)

    assert history.items == ()


async def test_a_score_run_cannot_be_read_by_another_workspace(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    ada = await new_run(engine, "ada")
    grace = await new_run(engine, "grace")
    score = await _record(app_sessions, ada)

    async with in_workspace(app_sessions, grace.workspace_id) as session:
        with pytest.raises(ScoreRunNotFoundError):
            await scoring.get_score_run(session, grace.workspace_id, score.id)
        with pytest.raises(IdeaNotFoundError):
            await scoring.score_history(session, grace.workspace_id, ada.idea_id)


async def test_a_score_run_of_an_archived_idea_is_not_found(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    score = await _record(app_sessions, run)
    await archive(engine, run.idea_id)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        with pytest.raises(ScoreRunNotFoundError):
            await scoring.get_score_run(session, run.workspace_id, score.id)


async def test_diff_gives_per_parameter_deltas_and_the_band_change(
    engine: AsyncEngine, app_sessions: Sessions
) -> None:
    run = await new_run(engine)
    a = await _record(app_sessions, run, _marks(10, 10, 0, 0, 3, 1))  # 54, advise
    b = await _record(app_sessions, run, _marks(10, 10, 5, 5, 5, 5))  # 75, build

    async with in_workspace(app_sessions, run.workspace_id) as session:
        delta = await scoring.diff(session, run.workspace_id, a.id, b.id)

    assert (delta.from_id, delta.to_id, delta.total_delta, delta.band_changed) == (
        a.id,
        b.id,
        21,
        True,
    )
    assert [(d.param, d.raw_delta, d.weighted_delta) for d in delta.params] == [
        (P.PROBLEM_SEVERITY, 0, 0.0),
        (P.UNIQUENESS, 0, 0.0),
        (P.MARKET_DEMAND, 5, 7.5),
        (P.VALUE, 5, 7.5),
        (P.FEASIBILITY, 2, 2.0),
        (P.TIMING, 4, 4.0),
    ]


async def test_diff_of_two_ideas_is_refused(engine: AsyncEngine, app_sessions: Sessions) -> None:
    run = await new_run(engine)
    other = await another_run(engine, run.workspace_id)
    a = await _record(app_sessions, run)
    b = await _record(app_sessions, other)

    async with in_workspace(app_sessions, run.workspace_id) as session:
        with pytest.raises(InvalidInputError):
            await scoring.diff(session, run.workspace_id, a.id, b.id)


async def _score_count(engine: AsyncEngine, run: Run) -> int:
    async with engine.connect() as conn:
        count = await conn.scalar(
            text("SELECT count(*) FROM scoring.score_runs WHERE idea_id = :id"),
            {"id": run.idea_id},
        )
    assert count is not None
    return int(count)
