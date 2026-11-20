"""The graph's state: ids, the stage and short summaries only.

The checkpoint stores this after every node, so it stays small and JSON-safe: documents,
search results and scores live in their module's tables and are read through services.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict
from uuid import UUID

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from metis.modules.ideas import Stage


class Budget(TypedDict):
    """Limits for one run; the caller loads them from the workspace's settings."""

    max_steps: int


class MetisState(TypedDict):
    """State of one run. ``stage`` is the run's working copy; the runner copies each change to
    ``ideas.stage`` (``agent/stage_sync.py``), so nodes never write it themselves.

    A checkpoint restores ``stage`` as a plain string (``Stage`` is a ``StrEnum``), so nodes
    compare it with ``==``, never ``is``.
    """

    run_id: str
    workspace_id: str
    idea_id: str
    stage: Stage
    messages: Annotated[list[AnyMessage], add_messages]
    summary: str
    step_count: int
    budget: Budget
    pending_approval: dict[str, Any] | None
    last_error: str | None
    # Researcher → Interviewer round trip (SHIP-238). Read with ``.get``: checkpoints written
    # before these fields existed do not have them.
    clarification: list[str]
    clarification_rounds: int
    # A post-run user message is handled by the Interviewer before the stage's next step.
    continuation_prompt: str | None
    continuation_done: bool
    # Set by the Researcher when the workspace has no Exa key: the run ends (SHIP-272).
    research_skipped: bool
    # Advisor (SHIP-241). ``rescore_after`` is the score run the user chose to revise and
    # rescore; the Scorer scores again once, then clears it. ``advice_stopped`` ends the run.
    rescore_after: str | None
    advice_stopped: bool


def initial_state(
    *,
    run_id: UUID,
    workspace_id: UUID,
    idea_id: UUID,
    stage: Stage,
    max_steps: int,
    continuation_prompt: str | None = None,
) -> MetisState:
    """The state a new run starts with."""
    return MetisState(
        run_id=str(run_id),
        workspace_id=str(workspace_id),
        idea_id=str(idea_id),
        stage=stage,
        messages=[],
        summary="",
        step_count=0,
        budget=Budget(max_steps=max_steps),
        pending_approval=None,
        last_error=None,
        clarification=[],
        clarification_rounds=0,
        research_skipped=False,
        rescore_after=None,
        advice_stopped=False,
        continuation_prompt=continuation_prompt,
        continuation_done=False,
    )
