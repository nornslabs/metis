"""Copies the graph's stage to ``ideas.stage`` after each node.

A run's working stage lives in the graph state; the idea's own stage is what a later run
starts from, so every change a node makes is saved there too. The write goes through the
``ideas`` module, so the transition table applies, and it is idempotent: a node that runs
again after a crash finds the idea already at its stage and writes nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from metis.modules import ideas
from metis.modules.ideas import Stage

if TYPE_CHECKING:
    from uuid import UUID

STAGE_KEY = "stage"


def stages_in(update: Mapping[str, Any]) -> list[Stage]:
    """The stages the nodes in one ``updates`` chunk set, in order.

    A chunk maps node name to that node's returned update; a node that sets no stage (and the
    ``__interrupt__`` entry, which is not a mapping) adds nothing.
    """
    return [
        Stage(node_update[STAGE_KEY])
        for node_update in update.values()
        if isinstance(node_update, Mapping) and node_update.get(STAGE_KEY) is not None
    ]


async def save_stage(
    session: AsyncSession, workspace_id: UUID, idea_id: UUID, stage: Stage
) -> None:
    """Move the idea to ``stage``; nothing happens when it is already there.

    A move the transition table refuses raises ``IllegalTransition``.
    """
    idea = await ideas.get_idea(session, workspace_id, idea_id)
    if idea.stage != stage:
        await ideas.transition(session, workspace_id, idea_id, stage)
