"""Score runs: record one from six parameter marks, and read, list and compare them.

Every function takes the caller's ``AsyncSession``, flushes but never commits and is scoped to
the workspace id as well as RLS. Score runs are immutable: nothing here updates or deletes one.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from metis.core.errors import (
    IdeaNotFoundError,
    InvalidInputError,
    RunNotFoundError,
    ScoreRunNotFoundError,
)
from metis.core.logging import bind_context, get_logger
from metis.core.outbox import DomainEvent, DomainEventType, add_event
from metis.helpers.validation import validate_input
from metis.modules import ideas
from metis.modules.scoring import repo
from metis.modules.scoring.dto import (
    NewParamScore,
    ParamDiff,
    Rubric,
    ScoreDiff,
    ScoreHistory,
    ScoreParam,
    ScoreParamResult,
    ScoreRun,
    ScoreRunSummary,
    ScoreSubmission,
    ScoreTrigger,
)
from metis.modules.scoring.models import ScoreParamRow, ScoreRunRow
from metis.modules.scoring.service import rubric as rubric_service
from metis.modules.scoring.service.rubric import band_for, total_from, weighted_points

logger = get_logger(__name__)


async def record_score(
    session: AsyncSession,
    workspace_id: UUID,
    idea_id: UUID,
    run_id: UUID,
    params: Sequence[NewParamScore],
    trigger: ScoreTrigger,
) -> ScoreRun:
    """Store a new score run from six parameter marks; the total and band are computed here.

    In one transaction: the score run and its params, a ``ScoreComputed`` outbox event and the
    idea's current score. Unknown or archived idea → ``IdeaNotFoundError``; a run of another
    idea (or none) → ``RunNotFoundError``; a missing, unknown or duplicate parameter, or an
    evidence rule broken → ``InvalidInputError``.
    """
    await ideas.get_idea(session, workspace_id, idea_id)
    run = await ideas.get_run(session, workspace_id, run_id)
    if run.idea_id != idea_id:
        raise RunNotFoundError()
    submission = validate_input(ScoreSubmission, params=tuple(params))
    rubric = await rubric_service.get_rubric(session)
    weighted = {
        entry.param: weighted_points(entry.raw, rubric.weights[entry.param])
        for entry in submission.params
    }
    total = total_from(weighted.values())
    band = band_for(total)
    await repo.score_runs.lock_idea(session, idea_id)  # one scorer at a time per idea
    previous = await repo.score_runs.latest_for_idea(session, workspace_id, idea_id)

    row = await repo.score_runs.create(
        session,
        workspace_id,
        idea_id,
        run_id,
        rubric_version_id=rubric.version,
        trigger=trigger.value,
        total=total,
        band=band.value,
    )
    param_rows = await repo.score_params.create_many(
        session,
        workspace_id,
        row.id,
        [_param_values(e, weighted[e.param]) for e in submission.params],
    )
    add_event(
        session,
        DomainEvent(
            workspace_id=workspace_id,
            type=DomainEventType.SCORE_COMPUTED,
            payload={
                "idea_id": str(idea_id),
                "score_run_id": str(row.id),
                "run_id": str(run_id),
                "total": total,
                "band": band.value,
                "trigger": trigger.value,
                "previous_total": None if previous is None else previous.total,
            },
        ),
    )
    await ideas.set_current_score(session, workspace_id, idea_id, total)
    bind_context(idea_id=str(idea_id), run_id=str(run_id), workspace_id=str(workspace_id))
    logger.info("score.recorded", score_run_id=str(row.id), total=total, band=band.value)
    return _view(row, rubric, param_rows)


async def latest_score(session: AsyncSession, workspace_id: UUID, idea_id: UUID) -> ScoreRun | None:
    """The newest score run of the idea, or ``None``; an unknown or archived idea is not found."""
    await ideas.get_idea(session, workspace_id, idea_id)
    row = await repo.score_runs.latest_for_idea(session, workspace_id, idea_id)
    return None if row is None else await _load_view(session, workspace_id, row)


async def score_history(session: AsyncSession, workspace_id: UUID, idea_id: UUID) -> ScoreHistory:
    """The idea's score runs without params, newest first."""
    await ideas.get_idea(session, workspace_id, idea_id)
    rows = await repo.score_runs.list_for_idea(session, workspace_id, idea_id)
    return ScoreHistory(items=tuple(_summary(row) for row in rows))


async def get_score_run(session: AsyncSession, workspace_id: UUID, score_run_id: UUID) -> ScoreRun:
    """A score run with its params; unknown, foreign or archived → ``ScoreRunNotFoundError``."""
    row = await _live_row(session, workspace_id, score_run_id)
    return await _load_view(session, workspace_id, row)


async def diff(session: AsyncSession, workspace_id: UUID, a_id: UUID, b_id: UUID) -> ScoreDiff:
    """Per-parameter deltas of run ``b`` over run ``a`` (``b − a``); both must be of one idea."""
    a = await get_score_run(session, workspace_id, a_id)
    b = await get_score_run(session, workspace_id, b_id)
    if a.idea_id != b.idea_id:
        raise InvalidInputError("The two score runs belong to different ideas.")
    before = {p.param: p for p in a.params}
    after = {p.param: p for p in b.params}
    return ScoreDiff(
        from_id=a.id,
        to_id=b.id,
        total_delta=b.total - a.total,
        band_changed=a.band is not b.band,
        params=tuple(_param_diff(p, before[p], after[p]) for p in ScoreParam),
    )


async def _live_row(session: AsyncSession, workspace_id: UUID, score_run_id: UUID) -> ScoreRunRow:
    """The score run of a live idea, else ``ScoreRunNotFoundError``."""
    row = await repo.score_runs.get(session, workspace_id, score_run_id)
    if row is None:
        raise ScoreRunNotFoundError()
    try:
        await ideas.get_idea(session, workspace_id, row.idea_id)
    except IdeaNotFoundError:
        raise ScoreRunNotFoundError() from None
    return row


async def _load_view(session: AsyncSession, workspace_id: UUID, row: ScoreRunRow) -> ScoreRun:
    stored = await repo.rubric.get(session, row.rubric_version_id)
    if stored is None:  # the FK makes this unreachable
        raise ScoreRunNotFoundError()
    rubric = rubric_service.rubric_of(stored.id, stored.weights)
    param_rows = await repo.score_params.list_for_run(session, workspace_id, row.id)
    return _view(row, rubric, param_rows)


def _param_values(entry: NewParamScore, weighted: Decimal) -> dict[str, object]:
    return {
        "param": entry.param.value,
        "raw": entry.raw,
        "weighted": weighted,
        "reason": entry.reason,
        "confidence": Decimal(str(entry.confidence)),
        "no_evidence": entry.no_evidence,
        "evidence": [item.model_dump() for item in entry.evidence],
    }


def _summary(row: ScoreRunRow) -> ScoreRunSummary:
    return ScoreRunSummary.model_validate(
        {
            "id": row.id,
            "idea_id": row.idea_id,
            "run_id": row.run_id,
            "rubric_version": row.rubric_version_id,
            "trigger": row.trigger,
            "total": row.total,
            "band": row.band,
            "created_at": row.created_at,
        }
    )


def _view(row: ScoreRunRow, rubric: Rubric, param_rows: Sequence[ScoreParamRow]) -> ScoreRun:
    by_param = {ScoreParam(p.param): p for p in param_rows}
    results = tuple(
        ScoreParamResult.model_validate(
            {
                "param": param,
                "weight": rubric.weights[param],
                "raw": by_param[param].raw,
                "weighted": by_param[param].weighted,
                "reason": by_param[param].reason,
                "confidence": by_param[param].confidence,
                "no_evidence": by_param[param].no_evidence,
                "evidence": by_param[param].evidence,
            }
        )
        for param in ScoreParam
    )
    return ScoreRun.model_validate(
        {**_summary(row).model_dump(), "weights": rubric.weights, "params": results}
    )


def _param_diff(param: ScoreParam, a: ScoreParamResult, b: ScoreParamResult) -> ParamDiff:
    return ParamDiff(
        param=param,
        raw_delta=b.raw - a.raw,
        weighted_delta=round(b.weighted - a.weighted, 2),
        confidence_delta=round(b.confidence - a.confidence, 2),
    )
