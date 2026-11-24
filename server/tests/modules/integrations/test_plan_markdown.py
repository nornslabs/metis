"""The Markdown export file: one snapshot, and the ways user text must not break it."""

from __future__ import annotations

import re
from pathlib import Path

from metis.modules.integrations.helpers.plan_markdown import render_plan_markdown
from metis.modules.planning import PlanStatus
from tests.modules.integrations.export_fixtures import (
    export_of,
    full_plan,
    phase,
    plan_of,
    score,
    task,
)

SNAPSHOT = Path(__file__).parent / "snapshots" / "plan_export.md"
FENCE = "`" * 3


def _outside_code(markdown: str) -> list[str]:
    """The lines that are not inside a code fence."""
    lines: list[str] = []
    inside = False
    for line in markdown.splitlines():
        if line.startswith(FENCE):
            inside = not inside
        elif not inside:
            lines.append(line)
    return lines


def _mermaid(markdown: str) -> str:
    match = re.search(rf"{FENCE}mermaid\n(.*?)\n{FENCE}", markdown, re.DOTALL)
    assert match, "no mermaid block"
    return match.group(1)


def test_a_full_plan_matches_the_snapshot() -> None:
    result = render_plan_markdown(export_of(full_plan(), run_score=score()))

    assert result == SNAPSHOT.read_text()


def test_the_same_data_gives_the_same_file() -> None:
    export = export_of(full_plan(), run_score=score())

    assert render_plan_markdown(export) == render_plan_markdown(export)


def test_an_idea_without_a_score_says_so_and_has_no_table() -> None:
    result = render_plan_markdown(export_of(full_plan()))

    assert "Not scored." in result
    assert "| Parameter |" not in result


def test_the_score_table_has_a_row_per_parameter_in_rubric_order() -> None:
    result = render_plan_markdown(export_of(full_plan(), run_score=score(72)))

    rows = [
        line.split(" | ")[0].removeprefix("| ") for line in result.splitlines() if " / 10 " in line
    ]
    assert rows == [
        "Problem severity",
        "Uniqueness",
        "Market demand",
        "Value",
        "Feasibility",
        "Timing",
    ]
    assert "**Total: 72 / 100** — Promising" in result


def test_the_header_names_the_plan_status() -> None:
    draft = render_plan_markdown(export_of(full_plan()))
    ready = render_plan_markdown(export_of(plan_of(*full_plan().phases, status=PlanStatus.READY)))

    assert "Plan: draft, version 3" in draft
    assert "Plan: ready, version 3" in ready


def test_the_graph_has_a_node_per_task_and_an_edge_per_dependency() -> None:
    graph = _mermaid(render_plan_markdown(export_of(full_plan())))

    assert len(re.findall(r'^\s+T\d+\["', graph, re.MULTILINE)) == 3
    assert sorted(re.findall(r"T\d+ --> T\d+", graph)) == ["T1 --> T2", "T1 --> T3", "T2 --> T3"]


def test_a_plan_without_tasks_has_no_graph_and_each_phase_says_so() -> None:
    result = render_plan_markdown(export_of(plan_of(phase(0, "Empty"))))

    assert "mermaid" not in result
    assert "No tasks in this phase." in result


def test_text_in_a_title_cannot_break_the_graph_or_a_heading() -> None:
    nasty = 'Say "hi" ] | <script>alert(1)</script> ' + FENCE
    result = render_plan_markdown(export_of(plan_of(phase(0, "P", task(1, nasty)))))

    graph = _mermaid(result)
    assert graph.count('"') % 2 == 0
    assert "<script>" not in result
    assert FENCE not in graph
    assert not any("\n" in line for line in graph.splitlines())


def test_an_unclosed_fence_in_a_description_cannot_swallow_the_rest_of_the_file() -> None:
    description = f"{FENCE}\nopen\n# not a heading"
    result = render_plan_markdown(
        export_of(plan_of(phase(0, "A", task(1, "One", description=description)), phase(1, "B")))
    )

    assert "### Phase 2 — B" in _outside_code(result)
    assert "# not a heading" not in _outside_code(result)


def test_the_spec_keeps_the_file_to_one_top_heading_and_closes_open_fences() -> None:
    spec = f"# Spec title\n\n## Problem\ntext\n{FENCE}py\n# a comment\n{FENCE}\n{FENCE}\n## inside"
    result = render_plan_markdown(export_of(full_plan(), spec=spec))

    top = [line for line in _outside_code(result) if re.match(r"# ", line)]
    assert len(top) == 1
    assert "### Problem" in result
    assert result.count(FENCE) % 2 == 0


def test_a_pipe_or_newline_in_a_label_stays_inside_the_label() -> None:
    result = render_plan_markdown(
        export_of(plan_of(phase(0, "P", task(1, "One", labels=("a|b", "line\nbreak")))))
    )

    assert "- Labels: a\\|b, line break" in result
