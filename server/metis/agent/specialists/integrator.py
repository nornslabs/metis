"""The Integrator: choose the Linear team, show the export preview, get the user's approval
(SHIP-252), then write the Linear project and its milestones (SHIP-253).

At ``planning`` the node (no model call):

1. reads the idea's plan, the workspace's saved Linear team and the refs of items already
   exported (``external_refs``);
2. loads the Linear read tools (Linear is required: a missing or expired connection fails the run)
   and lists the teams. A saved team that is still there is used; otherwise the user picks one in
   a ``choose_team`` interrupt;
3. builds the preview and asks for approval in an ``export_approval`` interrupt;
4. records the decision (who, when, the preview) in ``export_jobs``, saves the chosen team, and
   on approval records it in state ``pending_approval`` (the gate the write tools check).

After an approval, and only if the plan is still the version the user saw, the node marks the
run's export job ``running`` and creates or updates the project and one milestone per phase
(``export_writes``). The run then ends (``export_state``) with the stage left at ``planning``;
the issues are a later step. Re-running the node after a resume replays the same interrupts in
the same order, so the team is saved only once both are answered, and the decision record is
idempotent per run. A re-run that finds the run's decision already recorded asks nothing and goes
straight to the writes, which carry on from the refs already saved (``_replay``).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.sessions import McpHttpClientFactory
from langgraph.config import get_stream_writer
from langgraph.types import interrupt
from redis.asyncio import Redis

from metis.adapters.flags import build_flag_provider
from metis.agent.specialists.stubs import SpecialistNode
from metis.agent.state import MetisState
from metis.agent.supervisor import Specialist
from metis.agent.tools.ask_user import CHOOSE_TEAM, EXPORT_APPROVAL
from metis.agent.tools.export_linear import (
    LIST_LABELS,
    LIST_TEAMS,
    read_label_names,
    read_teams,
)
from metis.agent.tools.export_preview import ExportPreview, ExportTeam, build_export_preview
from metis.agent.tools.export_project import ProjectScore, idea_url
from metis.agent.tools.export_writes import ProjectSource, write_project_and_milestones
from metis.agent.tools.mcp import McpRunContext, load_mcp_tools
from metis.agent.tools.mcp_policy import INTEGRATOR_POLICY, ApprovalLedger
from metis.agent.tools.research_kb import SessionOpener
from metis.core.config import get_settings
from metis.core.errors import (
    ExportPlanChangedError,
    NoLinearTeamError,
    NoPlanToExportError,
    PlanNotFoundError,
)
from metis.core.events import RunEventType, publish
from metis.core.logging import get_logger
from metis.core.ports import FeatureFlags, FlagContext
from metis.helpers.http import ClientFactory
from metis.helpers.time import utcnow
from metis.modules import ideas, identity, integrations, planning, scoring
from metis.modules.integrations import (
    ExportJob,
    ExportStatus,
    IntegrationProvider,
    LocalKind,
)
from metis.modules.planning import Plan

EXPORT_ACTION = "export"
# A recorded job in these statuses has an approval whose writes may still need to carry on.
_WRITING_STATUSES = frozenset({ExportStatus.APPROVED, ExportStatus.RUNNING})
STATE_APPROVED = "approved"
STATE_DECLINED = "declined"
NOTICE_ISSUES_PENDING = "export.issues_pending"
NOTICE_ISSUES_PENDING_TEXT = (
    "The project and milestones are in Linear. Creating the issues is not available yet."
)

logger = get_logger(__name__)


def build_integrator(
    open_session: SessionOpener,
    redis: Redis,
    make_client: ClientFactory,
    mcp_http_client: McpHttpClientFactory | None = None,
    flags: FeatureFlags | None = None,
) -> SpecialistNode:
    """The Integrator node for one run."""
    _flags = flags or build_flag_provider()
    settings = get_settings()

    async def node(state: MetisState) -> dict[str, Any]:
        workspace_id, idea_id = UUID(state["workspace_id"]), UUID(state["idea_id"])
        run_id = UUID(state["run_id"])
        ledger = ApprovalLedger(state.get("pending_approval"))
        context = McpRunContext(
            workspace_id=workspace_id,
            run_id=run_id,
            open_session=open_session,
            redis=redis,
            make_client=make_client,
            mcp_http_client=mcp_http_client,
            specialist=Specialist.INTEGRATOR.value,
        )
        source = await _read_plan(open_session, workspace_id, idea_id)
        async with open_session(workspace_id) as session:
            decided = await integrations.get_export_decision(session, workspace_id, run_id)
        if decided is not None:
            return await _replay(
                state, context, ledger, open_session, source, decided, flags=_flags
            )
        tools = {t.name: t for t in await load_mcp_tools(context, INTEGRATOR_POLICY, ledger)}
        team, chosen = await _team(tools, source.saved_team_id)
        preview = await _preview(tools, source, team)
        logger.info(
            "export.preview_built",
            milestones=preview.milestones.total,
            issues=preview.issues.total,
            links=preview.blocked_by_links,
        )
        answer = interrupt({"type": EXPORT_APPROVAL, "preview": preview.model_dump(mode="json")})
        approved, decided_by, previewed = _decision(answer)
        await _record(
            open_session, workspace_id, run_id, source, preview, approved, decided_by, previewed
        )
        if chosen:
            await _save_team(open_session, workspace_id, team)
        logger.info("export.decided", approved=approved)
        if approved:
            flag_context = FlagContext(
                workspace_id=workspace_id,
                environment=settings.app_env,
                custom_attributes={},
            )
            if not await _flags.is_enabled("linear_enabled", flag_context):
                logger.info("export.skipped_linear_disabled")
                get_stream_writer()(
                    {
                        "type": RunEventType.NOTICE.value,
                        "code": "export.skipped_linear_disabled",
                        "text": "Linear export is skipped: the linear_enabled kill switch is off.",
                    }
                )
            else:
                await _write(context, ledger, tools, source, preview, previewed)
        return await _finish(state, context, ledger, approved)

    return node


async def _replay(
    state: MetisState,
    context: McpRunContext,
    ledger: ApprovalLedger,
    open_session: SessionOpener,
    source: _Source,
    decided: ExportJob,
    flags: FeatureFlags | None = None,
) -> dict[str, Any]:
    """Finish a run whose decision was already recorded (a re-run after a crash between the
    record and the checkpoint). It asks nothing: the saved team may already have changed, which
    would shift the order of the interrupts the stored answers belong to."""
    preview = ExportPreview.model_validate(decided.summary)
    approved = decided.status in _WRITING_STATUSES
    if preview.team.id != source.saved_team_id:
        await _save_team(open_session, context.workspace_id, preview.team)
    logger.info("export.decision_replayed", approved=approved)
    if approved:
        _flags = flags or build_flag_provider()
        settings = get_settings()
        flag_context = FlagContext(
            workspace_id=context.workspace_id,
            environment=settings.app_env,
            custom_attributes={},
        )
        if not await _flags.is_enabled("linear_enabled", flag_context):
            logger.info("export.skipped_linear_disabled")
        else:
            tools = {t.name: t for t in await load_mcp_tools(context, INTEGRATOR_POLICY, ledger)}
            await _write(
                context, ledger, tools, source, preview, _stored_plan_version(decided)
            )
    return await _finish(state, context, ledger, approved)


class _Source:
    """What the node reads before it talks to Linear."""

    def __init__(
        self,
        idea_id: UUID,
        title: str,
        plan: Plan,
        saved_team_id: str | None,
        project_ref: bool,
        phase_refs: frozenset[UUID],
        task_refs: frozenset[UUID],
        spec_text: str,
        score: ProjectScore | None,
    ) -> None:
        self.idea_id = idea_id
        self.title = title
        self.plan = plan
        self.saved_team_id = saved_team_id
        self.project_ref = project_ref
        self.phase_refs = phase_refs
        self.task_refs = task_refs
        self.spec_text = spec_text
        self.score = score


async def _read_plan(open_session: SessionOpener, workspace_id: UUID, idea_id: UUID) -> _Source:
    async with open_session(workspace_id) as session:
        idea = await ideas.get_idea(session, workspace_id, idea_id)
        spec = (await ideas.get_spec_overview(session, workspace_id, idea_id)).confirmed
        if spec is None:
            raise NoPlanToExportError("The idea has no confirmed spec to export")
        try:
            plan = await planning.get_plan(session, workspace_id, idea_id, spec.id)
        except PlanNotFoundError:
            raise NoPlanToExportError("The idea has no plan to export") from None
        tasks = [task for phase in plan.phases for task in phase.tasks]
        if not tasks:
            raise NoPlanToExportError("The plan has no tasks to export")
        saved = (await identity.get_settings_overview(session, workspace_id)).settings
        provider = IntegrationProvider.LINEAR
        project = await integrations.list_external_refs(
            session, workspace_id, provider, LocalKind.IDEA, [idea_id]
        )
        phases = await integrations.list_external_refs(
            session, workspace_id, provider, LocalKind.PHASE, [p.id for p in plan.phases]
        )
        task_refs = await integrations.list_external_refs(
            session, workspace_id, provider, LocalKind.TASK, [t.id for t in tasks]
        )
        latest = await scoring.latest_score(session, workspace_id, idea_id)
    return _Source(
        idea_id,
        idea.title,
        plan,
        saved.linear_team_id,
        idea_id in project,
        frozenset(phases),
        frozenset(task_refs),
        spec.content_md,
        None if latest is None else ProjectScore(latest.total, latest.band.value),
    )


async def _team(tools: dict[str, BaseTool], saved_team_id: str | None) -> tuple[ExportTeam, bool]:
    """The team to export to, and whether the user just chose it (so it must be saved)."""
    teams = await read_teams(tools.get(LIST_TEAMS))
    if not teams:
        raise NoLinearTeamError(
            "Linear has no team to export to; create one in Linear first",
            meta={"provider": IntegrationProvider.LINEAR.value},
        )
    by_id = {team["id"]: team for team in teams}
    if saved_team_id is not None and saved_team_id in by_id:
        return _export_team(by_id[saved_team_id]), False
    answer = interrupt({"type": CHOOSE_TEAM, "teams": teams, "saved_team_id": saved_team_id})
    chosen = by_id.get(str(answer.get("team_id")) if isinstance(answer, dict) else "")
    if chosen is None:
        raise NoLinearTeamError("The chosen team is not in Linear")
    return _export_team(chosen), True


async def _preview(tools: dict[str, BaseTool], source: _Source, team: ExportTeam) -> ExportPreview:
    labels = await read_label_names(tools.get(LIST_LABELS))
    return build_export_preview(
        team=team,
        idea_title=source.title,
        plan=source.plan,
        project_exists=source.project_ref,
        phase_refs=source.phase_refs,
        task_refs=source.task_refs,
        linear_labels=labels,
    )


async def _record(
    open_session: SessionOpener,
    workspace_id: UUID,
    run_id: UUID,
    source: _Source,
    preview: ExportPreview,
    approved: bool,
    decided_by: UUID,
    previewed_plan_version: int | None,
) -> None:
    """Record the decision. ``summary`` keeps the plan version the user saw; an approval that
    names none keeps the current one (the export then stops, see ``_write``)."""
    version = source.plan.version if previewed_plan_version is None else previewed_plan_version
    summary = {
        **preview.model_dump(mode="json"),
        "plan_id": str(source.plan.id),
        "plan_version": version,
    }
    async with open_session(workspace_id) as session:
        await integrations.record_export_decision(
            session,
            workspace_id,
            idea_id=source.idea_id,
            plan_id=source.plan.id,
            run_id=run_id,
            approved=approved,
            decided_by=decided_by,
            decided_at=utcnow(),
            summary=summary,
        )


async def _save_team(open_session: SessionOpener, workspace_id: UUID, team: ExportTeam) -> None:
    async with open_session(workspace_id) as session:
        await identity.set_linear_team(session, workspace_id, team.id)
    logger.info("export.team_chosen", team_id=team.id)


async def _write(
    context: McpRunContext,
    ledger: ApprovalLedger,
    tools: dict[str, BaseTool],
    source: _Source,
    preview: ExportPreview,
    previewed_plan_version: int | None,
) -> None:
    """Create or update the project and milestones for an approved export.

    Stops before any write if the plan is not the version the user saw (an approval that names no
    version counts as a mismatch: the guard never passes by default). The approval is recorded
    in the ledger first (the write tools refuse to run without it), then the export job moves to
    ``running``.
    """
    if previewed_plan_version is None or source.plan.version != previewed_plan_version:
        raise ExportPlanChangedError(
            "The plan changed after you approved the export; export again to review it",
            meta={
                "approved_version": previewed_plan_version,
                "current_version": source.plan.version,
            },
        )
    ledger.grant(EXPORT_ACTION, preview.summary_line())
    async with context.open_session(context.workspace_id) as session:
        await integrations.mark_export_running(session, context.workspace_id, context.run_id)
    await write_project_and_milestones(
        context,
        tools,
        ProjectSource(
            idea_id=source.idea_id,
            title=source.title,
            url=idea_url(get_settings().web_base_url, source.idea_id),
            spec_text=source.spec_text,
            score=source.score,
            plan=source.plan,
            team_id=preview.team.id,
        ),
    )


async def _finish(
    state: MetisState, context: McpRunContext, ledger: ApprovalLedger, approved: bool
) -> dict[str, Any]:
    update: dict[str, Any] = {
        "export_state": STATE_APPROVED if approved else STATE_DECLINED,
        "step_count": state["step_count"] + 1,
    }
    if approved:
        update["pending_approval"] = ledger.record
        await publish(
            str(context.run_id),
            RunEventType.NOTICE,
            {"code": NOTICE_ISSUES_PENDING, "text": NOTICE_ISSUES_PENDING_TEXT},
            redis=context.redis,
        )
    get_stream_writer()(
        {"type": RunEventType.NODE_FINISHED.value, "node": Specialist.INTEGRATOR.value}
    )
    return update


def _stored_plan_version(job: ExportJob) -> int | None:
    version = job.summary.get("plan_version")
    return version if isinstance(version, int) and not isinstance(version, bool) else None


def _decision(answer: object) -> tuple[bool, UUID, int | None]:
    """``(approved, decided_by, plan_version)`` from the resume value. The API stamps
    ``decided_by`` and the plan version the preview showed (``None`` when it names none)."""
    if not isinstance(answer, dict) or not isinstance(answer.get("approved"), bool):
        raise ValueError("The export approval answer must be {approved: bool}")
    if "decided_by" not in answer:
        raise ValueError("The export approval answer names no user (the resume route adds one)")
    version = answer.get("plan_version")
    previewed = version if isinstance(version, int) and not isinstance(version, bool) else None
    return answer["approved"], UUID(str(answer["decided_by"])), previewed


def _export_team(team: dict[str, str]) -> ExportTeam:
    return ExportTeam(id=team["id"], name=team["name"])
