"""The Architect: drafts the idea's spec and, for a software idea, its HLD, then waits for the
user to review and confirm them.

At ``spec_draft`` it runs a tool-calling loop (``build_react_specialist``) over the architect
prompt and ``save_spec``, on the run's ``spec`` chat model, seeded with the idea, its interview,
the research, the score and the suggestions the user accepted. The saved draft is version 1 of
the idea's spec. For a software idea (``kind`` is ``software``, which ``save_spec`` sets) a second
loop then writes the HLD for that version (SHIP-460): a blueprint in the build language the user
named, or, when nothing names one, the user's answer to a single question. The node then pauses
on a ``spec_review`` interrupt; the user edits (each edit is a new version, and the HLD is marked
stale) and confirms through the spec routes, which resume the run. Once resumed, the node writes
a fresh HLD only if the latest HLD is stale (the confirmed text differs from the one it was
written for), then moves the run to ``spec_confirmed``. A spec that cannot be drafted (two
refused ``save_spec`` calls, or no call) fails the run with ``spec.invalid_submission``. An HLD
that cannot be written does not fail the run: it is logged and the spec review goes on without
one.

The first HLD is written only while the idea is still at ``spec_draft``. The node re-runs from
its start on every resume, and the confirm route has moved the idea to ``spec_confirmed`` before
it resumes the run: a re-run after the confirmation must not start a new HLD loop, whose
question would take the confirmation as its answer.

The node is safe to re-run: when the idea already has a spec and an HLD (a crash re-run, the
re-run after the interrupt resumes, or an earlier run's draft) it makes no model call and goes
straight to the review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langgraph.config import get_stream_writer
from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession

from metis.agent.llm import LLMGateway
from metis.agent.prompts import load_specialist_prompt
from metis.agent.specialists.base import build_react_specialist, invoke_loop
from metis.agent.specialists.idea_context import idea_seed_parts
from metis.agent.specialists.stubs import SpecialistNode
from metis.agent.state import MetisState
from metis.agent.supervisor import Specialist
from metis.agent.tools.ask_user import SPEC_REVIEW
from metis.agent.tools.hld import SAVE_HLD, HldLedger, HldRefused, hld_tools
from metis.agent.tools.research_kb import ResearchScope, SessionOpener
from metis.agent.tools.scoring import SourceBook
from metis.agent.tools.spec import SAVE_SPEC, SpecLedger, SpecRefused, spec_tools
from metis.core.errors import ErrorCode
from metis.core.events import RunEventType
from metis.core.logging import get_logger
from metis.modules import ideas, scoring
from metis.modules.ideas import IdeaKind, SpecHld, SpecVersion, Stage
from metis.modules.scoring import SuggestionStatus

PROMPT = "architect"
HLD_PROMPT = "architect_hld"
PURPOSE = "spec"
# Graph supersteps: the model call and its save, with room for one refused attempt.
STEP_LIMIT = 15

logger = get_logger(__name__)


def build_architect(gateway: LLMGateway, open_session: SessionOpener) -> SpecialistNode:
    """The Architect node for one run."""

    async def node(state: MetisState) -> dict[str, Any]:
        scope = ResearchScope(
            workspace_id=UUID(state["workspace_id"]),
            idea_id=UUID(state["idea_id"]),
            run_id=UUID(state["run_id"]),
            open_session=open_session,
            gateway=gateway,
        )
        async with scope.session() as session:
            overview = await ideas.get_spec_overview(session, scope.workspace_id, scope.idea_id)
        latest = overview.latest
        if latest is None:
            drafted = await _draft(scope)
            if isinstance(drafted, str):
                return _finish_node(state, {"last_error": drafted})
            latest = drafted
        await _ensure_hld(scope)
        await _review(scope, latest)
        await refresh_stale_hld(scope)
        return _finish_node(state, {"stage": Stage.SPEC_CONFIRMED})

    return node


async def _draft(scope: ResearchScope) -> SpecVersion | str:
    """Run the loop; the saved version, or the error code to fail the run with."""
    ledger = SpecLedger()
    async with scope.session() as session:
        model = await scope.gateway.chat_model(session, PURPOSE)
        seed = await _seed(session, scope)
    loop = build_react_specialist(
        load_specialist_prompt(PROMPT),
        spec_tools(scope, ledger),
        model,
        step_limit=STEP_LIMIT,
        finish_tools={SAVE_SPEC},
        refusals=(SpecRefused,),
        resumable=False,
    )
    if not await invoke_loop(loop, seed):
        logger.warning("spec.step_limit_reached")
        return ErrorCode.RUN_STEP_LIMIT_REACHED.value
    if ledger.saved is None:
        logger.warning("spec.no_valid_spec", refusals=ledger.refusals)
        return ErrorCode.SPEC_INVALID_SUBMISSION.value
    async with scope.session() as session:
        return await ideas.get_spec(session, scope.workspace_id, scope.idea_id)


@dataclass(frozen=True)
class _HldState:
    """What the HLD steps decide on, read in one session: whether the idea is software, whether
    it is still a draft (not yet confirmed), its latest spec version and its newest HLD
    (``stale`` already worked out)."""

    software: bool
    drafting: bool
    latest: SpecVersion | None
    hld: SpecHld | None


async def _hld_state(scope: ResearchScope) -> _HldState:
    async with scope.session() as session:
        idea = await ideas.get_idea(session, scope.workspace_id, scope.idea_id)
        overview = await ideas.get_spec_overview(session, scope.workspace_id, scope.idea_id)
    return _HldState(
        software=idea.kind is IdeaKind.SOFTWARE,
        drafting=idea.stage is Stage.SPEC_DRAFT,
        latest=overview.latest,
        hld=overview.hld,
    )


async def _ensure_hld(scope: ResearchScope) -> None:
    """Write the first HLD of a software idea's spec, before the review. Nothing is written for
    another kind of idea, when an HLD already exists (a re-run adds nothing) and once the spec was
    confirmed (a re-run after the confirmation)."""
    state = await _hld_state(scope)
    if state.software and state.drafting and state.hld is None and state.latest is not None:
        await _write_hld(scope, state.latest, previous_language=None)


async def refresh_stale_hld(scope: ResearchScope) -> None:
    """After the user confirmed, and before an export's preview: write a fresh HLD when the
    confirmed spec text is not the one the latest HLD was written for. No call when the HLD is
    current, and none when there is no HLD (the first one could not be written; asking for a
    language now would be after the review).
    """
    state = await _hld_state(scope)
    if state.software and state.hld is not None and state.hld.stale and state.latest is not None:
        await _write_hld(scope, state.latest, previous_language=state.hld.build_language)


async def _write_hld(
    scope: ResearchScope, spec: SpecVersion, *, previous_language: str | None
) -> None:
    """Run the HLD loop for ``spec``. With a ``previous_language`` (the earlier HLD's) the loop
    never asks; it keeps that language unless the spec names another. A failure is logged,
    never raised: the review goes on without it."""
    ledger = HldLedger()
    async with scope.session() as session:
        model = await scope.gateway.chat_model(session, PURPOSE)
        seed = await _seed(session, scope)
    seed = "\n\n".join([seed, _spec_text(spec), _language_text(previous_language)])
    loop = build_react_specialist(
        load_specialist_prompt(HLD_PROMPT),
        hld_tools(scope, ledger, spec, may_ask=previous_language is None),
        model,
        step_limit=STEP_LIMIT,
        finish_tools={SAVE_HLD},
        refusals=(HldRefused,),
        resumable=previous_language is None,
    )
    if not await invoke_loop(loop, seed):
        logger.warning("hld.step_limit_reached", spec_number=spec.number)
    elif ledger.saved is None:
        logger.warning("hld.not_saved", spec_number=spec.number, refusals=ledger.refusals)


def _spec_text(spec: SpecVersion) -> str:
    return f"The product spec (version {spec.number}):\n\n{spec.content_md}"


def _language_text(previous_language: str | None) -> str:
    if previous_language is None:
        return "Build language: not decided yet. Look for it in the idea and the interview."
    return (
        f"Build language: {previous_language}, from the earlier HLD. Keep it unless the spec now "
        "names a different language or stack. Do not ask."
    )


async def _review(scope: ResearchScope, draft: SpecVersion) -> None:
    """Pause until the user confirms; nothing runs before this that cannot be repeated."""
    async with scope.session() as session:
        latest = await ideas.get_spec(session, scope.workspace_id, scope.idea_id)
        idea = await ideas.get_idea(session, scope.workspace_id, scope.idea_id)
    shown = latest if latest.number >= draft.number else draft
    interrupt(
        {
            "type": SPEC_REVIEW,
            "spec_version_id": str(shown.id),
            "number": shown.number,
            "kind": idea.kind.value if idea.kind else None,
        }
    )


async def _seed(session: AsyncSession, scope: ResearchScope) -> str:
    """What the model starts from: the idea, interview, research, score and accepted advice."""
    parts = await idea_seed_parts(session, scope, SourceBook())
    parts.append(await _score_text(session, scope))
    parts.append(await _accepted_text(session, scope))
    return "\n\n".join(parts)


async def _score_text(session: AsyncSession, scope: ResearchScope) -> str:
    score = await scoring.latest_score(session, scope.workspace_id, scope.idea_id)
    if score is None:
        return "Score: none."
    lines = [f"Score: {score.total} of 100 ({score.band.value})."]
    lines += [f"- {p.param.value}: {p.raw}/10. {p.reason}" for p in score.params]
    return "\n".join(lines)


async def _accepted_text(session: AsyncSession, scope: ResearchScope) -> str:
    listed = await scoring.list_suggestions(session, scope.workspace_id, scope.idea_id)
    accepted = [s for s in listed.items if s.status is SuggestionStatus.ACCEPTED]
    if not accepted:
        return "Accepted improvements: none."
    lines = [f"- {s.kind.value}: {s.title}. {s.rationale}" for s in accepted]
    return "Accepted improvements:\n" + "\n".join(lines)


def _finish_node(state: MetisState, update: dict[str, Any]) -> dict[str, Any]:
    get_stream_writer()(
        {"type": RunEventType.NODE_FINISHED.value, "node": Specialist.ARCHITECT.value}
    )
    return {**update, "step_count": state["step_count"] + 1}
