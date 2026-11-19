"""Which stages ``stages_in`` reads from one ``updates`` chunk of the graph's stream."""

from __future__ import annotations

from metis.agent.stage_sync import stages_in
from metis.modules.ideas import Stage


def test_it_reads_the_stage_a_node_set() -> None:
    update = {"researcher": {"stage": Stage.SCORING, "step_count": 3}}

    assert stages_in(update) == [Stage.SCORING]


def test_it_reads_a_stage_restored_from_a_checkpoint_as_plain_text() -> None:
    assert stages_in({"interviewer": {"stage": "researching"}}) == [Stage.RESEARCHING]


def test_a_node_that_sets_no_stage_adds_nothing() -> None:
    update = {"supervisor": {}, "researcher": {"research_skipped": True, "step_count": 1}}

    assert stages_in(update) == []


def test_an_interrupt_entry_adds_nothing() -> None:
    assert stages_in({"__interrupt__": ("question",)}) == []
