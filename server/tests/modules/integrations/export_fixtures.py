"""A fixed idea, spec, score and plan for the Markdown export tests (no database)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from metis.modules.ideas import Idea, SpecSource, SpecVersion
from metis.modules.integrations.helpers.plan_markdown import PlanExport
from metis.modules.planning import CriticalPath, Phase, Plan, PlanStatus, Task
from metis.modules.scoring import ScoreBand, ScoreParam, ScoreParamResult, ScoreRun, ScoreTrigger

NOW = datetime(2026, 1, 1, tzinfo=UTC)
SPEC = "## Problem\nFreelancers lose track of leads.\n\n## Core features\n- Pipeline\n- Reminders\n"
WEIGHTS = {
    ScoreParam.PROBLEM_SEVERITY: 20,
    ScoreParam.UNIQUENESS: 15,
    ScoreParam.MARKET_DEMAND: 20,
    ScoreParam.VALUE: 20,
    ScoreParam.FEASIBILITY: 15,
    ScoreParam.TIMING: 10,
}


def uid(number: int) -> UUID:
    return UUID(int=number)


def task(
    number: int,
    title: str,
    *,
    position: int = 0,
    description: str = "",
    labels: tuple[str, ...] = (),
    blocked_by: tuple[int, ...] = (),
    estimate: int = 3,
) -> Task:
    return Task(
        id=uid(number),
        position=position,
        title=title,
        description=description,
        estimate=estimate,
        labels=labels,
        parent_task_id=None,
        blocked_by=tuple(uid(n) for n in blocked_by),
    )


def phase(number: int, name: str, *tasks: Task) -> Phase:
    return Phase(
        id=uid(100 + number),
        position=number,
        name=name,
        goal=f"Goal of {name}",
        exit_criteria=f"{name} is done",
        tasks=tasks,
    )


def plan_of(*phases: Phase, status: PlanStatus = PlanStatus.DRAFT) -> Plan:
    return Plan(
        id=uid(200),
        idea_id=uid(1),
        spec_version_id=uid(2),
        status=status,
        version=3,
        ready_at=None,
        created_at=NOW,
        updated_at=NOW,
        phases=phases,
        critical_path=CriticalPath(task_ids=(), points=0),
    )


def score(total: int = 72, band: ScoreBand = ScoreBand.PROMISING) -> ScoreRun:
    return ScoreRun(
        id=uid(3),
        idea_id=uid(1),
        run_id=uid(4),
        rubric_version=1,
        trigger=ScoreTrigger.MANUAL,
        total=total,
        band=band,
        created_at=NOW,
        weights=WEIGHTS,
        params=tuple(
            ScoreParamResult(
                param=param,
                weight=weight,
                raw=7,
                weighted=weight * 0.7,
                reason="Because.",
                confidence=0.7,
                no_evidence=False,
                evidence=(),
            )
            for param, weight in WEIGHTS.items()
        ),
    )


def export_of(
    plan: Plan,
    *,
    title: str = "Pocket CRM",
    spec: str = SPEC,
    run_score: ScoreRun | None = None,
) -> PlanExport:
    return PlanExport(
        idea=Idea(
            id=uid(1),
            workspace_id=uid(5),
            created_by=uid(6),
            title=title,
            raw_text="A tiny CRM.",
            kind=None,
            stage="planning",
            current_score=None if run_score is None else run_score.total,
            version=1,
            created_at=NOW,
            updated_at=NOW,
        ),
        spec=SpecVersion(
            id=uid(2),
            idea_id=uid(1),
            number=1,
            source=SpecSource.AGENT,
            content_md=spec,
            sections={},
            run_id=None,
            created_by=None,
            created_at=NOW,
        ),
        score=run_score,
        plan=plan,
    )


def full_plan() -> Plan:
    """Three phases with a cross-phase dependency, labels, and a phase without tasks."""
    return plan_of(
        phase(
            0,
            "Foundations",
            task(
                1,
                "Set up the repo",
                labels=("chore", "server"),
                description="Create it.\n\nThen push.",
            ),
            task(2, "Design the schema", position=1, estimate=5, blocked_by=(1,)),
        ),
        phase(1, "Quiet phase"),
        phase(
            2,
            "Launch",
            task(3, "Ship the pipeline", labels=("feature",), blocked_by=(1, 2), estimate=8),
        ),
    )
