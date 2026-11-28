"""The Planner's tools: ``propose_phases`` (pauses for the user) and ``save_plan``.

``propose_phases`` gives the phases the model wants, calls ``interrupt()`` with them and returns
the list the user left. That reviewed list is the only phase list ``save_plan`` may use: the
model gives tasks and points at phases by their index. Phases are not stored before the tasks
exist (a plan needs tasks), so they live in the interrupt and the resume value.

``save_plan`` builds a ``planning.PlanInput`` and saves it as the plan for the confirmed spec
version. A plan the planning module refuses (cycle, bad estimate, unknown phase or task, and so
on) comes back to the model as a message it can act on. The first refusal lets the model try
again; the second closes the tool, and the node then fails the run instead of storing a plan it
cannot stand behind.

A node that calls these tools is re-run from its start on resume; the loop continues from its
checkpoint, so ``propose_phases`` returns the saved answer and the model is not called again.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel, Field, ValidationError

from metis.agent.tools.ask_user import PHASE_REVIEW
from metis.agent.tools.issue_brief import REQUIRED_SECTIONS, heading, missing_sections
from metis.agent.tools.research_kb import ResearchScope
from metis.core.errors import InvalidPlanError
from metis.core.logging import get_logger
from metis.helpers.dto import JsonList
from metis.modules import ideas, planning
from metis.modules.ideas import PhaseReviewResume
from metis.modules.planning import ESTIMATES, Plan

PROPOSE_PHASES = "propose_phases"
SAVE_PLAN = "save_plan"
MIN_PHASES = 3
MAX_PHASES = 7
MAX_REFUSALS = 2
MAX_BRIEF_PROBLEMS_SHOWN = 5
CLOSED = "Saving is closed: two attempts were refused. Stop."
SAVED = "Plan saved."
NO_PHASES_YET = f"Nothing was saved. Call {PROPOSE_PHASES} first; the phases come from the review."
SAVE_AGAIN = "Fix this and save the whole plan again."

logger = get_logger(__name__)


class PlanRefused(Exception):
    """A call the model must fix; its text is what the model reads."""

    def __repr__(self) -> str:
        return str(self)


@dataclass
class PlanLedger:
    """What the loop did: the phases the user approved (``None`` yet), the plan it saved
    (``None`` yet) and how many ``save_plan`` calls were refused."""

    phases: tuple[planning.PhaseInput, ...] | None = None
    saved: Plan | None = None
    refusals: int = 0


class PhaseArg(BaseModel):
    name: str = Field(default="", description="Short phase name, e.g. `Foundations`.")
    goal: str = Field(default="", description="What the phase achieves.")
    exit_criteria: str = Field(default="", description="How to tell the phase is done.")


class ProposePhasesArgs(BaseModel):
    phases: JsonList[PhaseArg] = Field(
        default_factory=list,
        description=f"{MIN_PHASES} to {MAX_PHASES} phases, from foundations to MVP, in order.",
    )


class TaskArg(BaseModel):
    key: str = Field(default="", description="A short unique key for this task, e.g. `t1`.")
    phase: int = Field(default=-1, description="Index (from 0) of the task's phase in the list.")
    title: str = Field(default="", description="Short title.")
    description: str = Field(
        default="",
        description=(
            "The issue brief in Markdown with `##` sections: Goal, Context, Requirements, "
            "Out of scope, Acceptance criteria, Dependencies, and an optional Agent notes."
        ),
    )
    estimate: int = Field(default=0, description=f"One of {', '.join(map(str, ESTIMATES))}.")
    labels: JsonList[str] = Field(default_factory=list, description="Up to 10 short labels.")
    component: str | None = Field(
        default=None,
        description="The one HLD component this task belongs to (exactly as listed), if given.",
    )
    blocked_by: JsonList[str] = Field(
        default_factory=list, description="Keys of the tasks that must finish first."
    )
    parent_key: str | None = Field(default=None, description="Key of the parent task, if any.")


class SavePlanArgs(BaseModel):
    """Fields default to empty so that a missing one is a refusal the tool counts and the model
    can fix, not an error the loop never counts."""

    tasks: JsonList[TaskArg] = Field(
        default_factory=list, description="Every task of every approved phase."
    )


def planning_tools(
    scope: ResearchScope,
    ledger: PlanLedger,
    spec_version_id: UUID,
    components: tuple[str, ...] = (),
) -> list[BaseTool]:
    """The Planner's allow-list: ``propose_phases`` and ``save_plan``. ``components`` are the
    idea's HLD component names (none when the idea has no HLD): every task must name one."""
    return [_propose_phases(ledger), _save_plan(scope, ledger, spec_version_id, components)]


def _propose_phases(ledger: PlanLedger) -> BaseTool:
    async def propose_phases(phases: list[PhaseArg]) -> str:
        proposed = _checked_phases(phases)
        answer = interrupt(
            {"type": PHASE_REVIEW, "phases": [p.model_dump(mode="json") for p in proposed]}
        )
        reviewed = PhaseReviewResume.model_validate(answer).model_dump(mode="json")["phases"]
        ledger.phases = tuple(planning.PhaseInput.model_validate(p) for p in reviewed)
        numbered = [{"phase": index, **phase} for index, phase in enumerate(reviewed)]
        return "The user approved these phases; write tasks for exactly these: " + json.dumps(
            numbered
        )

    return StructuredTool.from_function(
        coroutine=propose_phases,
        name=PROPOSE_PHASES,
        description=(
            f"Propose {MIN_PHASES} to {MAX_PHASES} phases and wait for the user to review them. "
            "Returns the phases the user approved, which may differ from yours."
        ),
        args_schema=ProposePhasesArgs,
    )


def _save_plan(
    scope: ResearchScope,
    ledger: PlanLedger,
    spec_version_id: UUID,
    components: tuple[str, ...],
) -> BaseTool:
    async def save_plan(tasks: list[TaskArg]) -> str:
        if ledger.refusals >= MAX_REFUSALS:
            return CLOSED
        if ledger.phases is None:
            # Also what a crash re-run after the review finds (the ledger is per visit): the
            # model proposes again. Raised, not returned, so the loop does not end on it.
            raise PlanRefused(NO_PHASES_YET)
        try:
            _check_briefs(tasks)
            data = _plan_input(ledger.phases, tasks, _checked_components(tasks, components))
            async with scope.session() as session:
                ledger.saved = await planning.save_plan(
                    session, scope.workspace_id, scope.idea_id, spec_version_id, data
                )
        except (InvalidPlanError, ValidationError, PlanRefused) as error:
            return _refuse(ledger, error)
        return SAVED

    return StructuredTool.from_function(
        coroutine=save_plan,
        name=SAVE_PLAN,
        description=(
            "Save the plan: the tasks of the approved phases, each with an estimate and the "
            "keys of the tasks that block it. The phases are the ones the user approved."
        ),
        args_schema=SavePlanArgs,
    )


def _refuse(ledger: PlanLedger, error: Exception) -> str:
    ledger.refusals += 1
    logger.warning("plan.save_refused", refusals=ledger.refusals, reason=_reason(error))
    if ledger.refusals >= MAX_REFUSALS:
        return CLOSED
    raise PlanRefused("Nothing was saved. " + _message(error))


def _reason(error: Exception) -> str:
    if isinstance(error, InvalidPlanError):
        return str((error.meta or {}).get("reason", "invalid"))
    return "bad_input"


def _message(error: Exception) -> str:
    if isinstance(error, InvalidPlanError):
        tasks = (error.meta or {}).get("tasks") or []
        named = f" Tasks involved: {', '.join(map(str, tasks))}." if tasks else ""
        return f"{error}{named} {SAVE_AGAIN}"
    if isinstance(error, ValidationError):
        problems = "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()[:5]
        )
        return f"A task is not valid ({problems})."
    return str(error)


def _check_briefs(tasks: list[TaskArg]) -> None:
    """Refuse a task whose description is not a usable issue brief, naming what is missing."""
    problems = [
        f"`{task.key}` lacks {', '.join(f'`{heading(name)}`' for name in missing)}"
        for task in tasks
        if (missing := missing_sections(task.description))
    ]
    if problems:
        needed = ", ".join(f"`{heading(name)}`" for name in REQUIRED_SECTIONS)
        raise PlanRefused(
            f"Every task description must be an issue brief with {needed} sections. "
            f"{'; '.join(problems[:MAX_BRIEF_PROBLEMS_SHOWN])}. {SAVE_AGAIN}"
        )


def _checked_components(tasks: list[TaskArg], components: tuple[str, ...]) -> dict[str, str]:
    """Each task key mapped to its component spelled as the HLD spells it. With no HLD the
    result is empty; otherwise a task with a missing or unknown component is refused."""
    if not components:
        return {}
    chosen: dict[str, str] = {}
    problems: list[str] = []
    for task in tasks:
        name = ideas.match_component(components, task.component)
        if name is None:
            problems.append(f"`{task.key}` has {task.component!r}")
        else:
            chosen[task.key] = name
    if problems:
        raise PlanRefused(
            "Every task needs exactly one component of the HLD: "
            f"{', '.join(f'`{name}`' for name in components)}. "
            f"{'; '.join(problems[:MAX_BRIEF_PROBLEMS_SHOWN])}. {SAVE_AGAIN}"
        )
    return chosen


def _checked_phases(phases: list[PhaseArg]) -> list[PhaseArg]:
    """The proposal, or a refusal the model can fix (no interrupt is raised for a bad one)."""
    if not MIN_PHASES <= len(phases) <= MAX_PHASES:
        raise PlanRefused(f"Propose {MIN_PHASES} to {MAX_PHASES} phases; you gave {len(phases)}.")
    try:
        for phase in phases:
            planning.PhaseInput.model_validate(phase.model_dump())
    except ValidationError as error:
        raise PlanRefused(f"A phase is not valid: {_message(error)}") from error
    return phases


def _plan_input(
    phases: tuple[planning.PhaseInput, ...], tasks: list[TaskArg], components: dict[str, str]
) -> planning.PlanInput:
    task_inputs = tuple(
        planning.TaskInput(
            key=t.key,
            phase=t.phase,
            title=t.title,
            description=t.description,
            estimate=t.estimate,
            labels=tuple(t.labels),
            component=components.get(t.key),
            parent_key=t.parent_key,
        )
        for t in tasks
    )
    deps = tuple(
        planning.DepInput(task_key=t.key, blocked_by_key=blocker)
        for t in tasks
        for blocker in t.blocked_by
    )
    return planning.PlanInput(phases=phases, tasks=task_inputs, deps=deps)
