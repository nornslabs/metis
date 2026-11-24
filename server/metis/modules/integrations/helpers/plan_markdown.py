"""An idea's spec, score and plan as one Markdown file people can share.

``render_plan_markdown`` is a pure function of stored data: the same input gives the same file,
byte for byte. Text written by users and models is never trusted to keep the file valid, so
every value goes through one of three treatments before it reaches the template:

- one-line text (titles, labels, goals): newlines collapsed, Markdown punctuation escaped;
- block text (task descriptions): quoted, so an unclosed code fence or a heading inside it
  cannot reach the rest of the file;
- the spec: headings lowered one level and any code fence left open is closed.

Mermaid node ids are generated, never taken from text.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import NamedTuple
from uuid import UUID

from jinja2 import Environment, PackageLoader, StrictUndefined

from metis.helpers.dto import FrozenModel
from metis.modules.ideas import Idea, SpecVersion
from metis.modules.planning import Phase, Plan, Task
from metis.modules.scoring import ScoreRun

MAX_RAW = 10
MAX_TOTAL = 100
GRAPH_LABEL_LIMIT = 50
MAX_HEADING_LEVEL = 6

_SPECIAL = re.compile(r"([\\`*_\[\]<>|])")
_WHITESPACE = re.compile(r"\s+")
_HEADING = re.compile(r"^(#{1,6})(?=\s)")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_GRAPH_ENTITIES = {'"': "#quot;", "<": "#lt;", ">": "#gt;", "`": "'"}

_env = Environment(
    loader=PackageLoader("metis.modules.integrations.helpers", "templates"),
    autoescape=False,  # Markdown, not HTML: every value is made safe in Python, above
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


class _TaskRef(NamedTuple):
    """What other tasks need to name a task: its ``T<n>`` name, title and phase number."""

    name: str
    title: str
    phase: int


class PlanExport(FrozenModel):
    """Everything the file is made of."""

    idea: Idea
    spec: SpecVersion
    score: ScoreRun | None
    plan: Plan


def render_plan_markdown(export: PlanExport) -> str:
    """The file's text for ``export``."""
    phases = list(export.plan.phases)
    refs = _task_refs(phases)
    context = {
        "title": _line(export.idea.title),
        "stage": _words(export.idea.stage.value),
        "plan_status": export.plan.status.value,
        "plan_version": export.plan.version,
        "score": _score_view(export.score),
        "spec": _lower_headings(export.spec.content_md),
        "graph": _graph(phases, refs),
        "phases": [_phase_view(number, phase, refs) for number, phase in enumerate(phases, 1)],
    }
    return _env.get_template("plan.md.j2").render(context)


# ------------------------------------------------------------------------------ text


def _line(text: str) -> str:
    """One line of text with Markdown punctuation escaped."""
    return _SPECIAL.sub(r"\\\1", _WHITESPACE.sub(" ", text).strip())


def _words(value: str) -> str:
    return value.replace("_", " ")


def _quote(text: str) -> str:
    """Block text as a blockquote, so nothing in it can open or close structure outside it."""
    lines = text.strip().splitlines()
    return "\n".join(f"> {line}".rstrip() for line in lines)


def _lower_headings(markdown: str) -> str:
    """The spec with each heading one level lower (the file keeps a single ``#``) and every
    code fence closed. Lines inside a code fence are left as written."""
    out: list[str] = []
    fence: str | None = None
    for line in markdown.strip().splitlines():
        match = _FENCE.match(line)
        if fence is None and match:
            fence = match.group(1)
        elif fence is not None and match and _closes(fence, match.group(1), line):
            fence = None
        elif fence is None:
            line = _HEADING.sub(_lowered, line)
        out.append(line)
    if fence is not None:
        out.append(fence[0] * len(fence))
    return "\n".join(out)


def _closes(opening: str, candidate: str, line: str) -> bool:
    same_kind = candidate[0] == opening[0] and len(candidate) >= len(opening)
    return same_kind and not line.strip()[len(candidate) :].strip()


def _lowered(match: re.Match[str]) -> str:
    return "#" * min(len(match.group(1)) + 1, MAX_HEADING_LEVEL)


# ------------------------------------------------------------------------------ score


def _score_view(score: ScoreRun | None) -> dict[str, object] | None:
    if score is None:
        return None
    return {
        "total": score.total,
        "max_total": MAX_TOTAL,
        "max_raw": MAX_RAW,
        "band": score.band.value.capitalize(),
        "rows": [
            {
                "label": _words(row.param.value).capitalize(),
                "weight": row.weight,
                "raw": row.raw,
                "confidence": f"{round(row.confidence * 100)}%",
            }
            for row in score.params
        ],
    }


# ------------------------------------------------------------------------------ plan


def _task_refs(phases: Sequence[Phase]) -> dict[UUID, _TaskRef]:
    """``T1``, ``T2``, … in plan order: the name a task has in the graph and in the text."""
    refs: dict[UUID, _TaskRef] = {}
    for phase_number, phase in enumerate(phases, 1):
        for task in phase.tasks:
            refs[task.id] = _TaskRef(f"T{len(refs) + 1}", task.title, phase_number)
    return refs


def _phase_view(number: int, phase: Phase, refs: dict[UUID, _TaskRef]) -> dict[str, object]:
    return {
        "number": number,
        "name": _line(phase.name),
        "goal": _line(phase.goal),
        "exit_criteria": _line(phase.exit_criteria),
        "tasks": [_task_view(task, refs) for task in phase.tasks],
    }


def _task_view(task: Task, refs: dict[UUID, _TaskRef]) -> dict[str, object]:
    # A blocker outside the plan cannot be stored; indexing fails loudly if one ever is.
    return {
        "ref": refs[task.id].name,
        "title": _line(task.title),
        "estimate": task.estimate,
        "labels": ", ".join(_line(label) for label in task.labels),
        "blocked_by": "; ".join(_blocker_text(refs[blocker]) for blocker in task.blocked_by),
        "description": _quote(task.description),
    }


def _blocker_text(blocker: _TaskRef) -> str:
    return f"{blocker.name} — {_line(blocker.title)} (phase {blocker.phase})"


# ------------------------------------------------------------------------------ graph


def _graph(phases: Sequence[Phase], refs: dict[UUID, _TaskRef]) -> str:
    """A Mermaid flowchart: a node per task, grouped by phase, an arrow from each blocker."""
    if not refs:
        return ""
    lines = ["flowchart TD"]
    for number, phase in enumerate(phases, 1):
        if not phase.tasks:
            continue
        lines.append(f'  subgraph P{number}["{_graph_label(f"Phase {number} — {phase.name}")}"]')
        lines.extend(_graph_node(refs[task.id]) for task in phase.tasks)
        lines.append("  end")
    lines.extend(
        f"  {refs[blocker].name} --> {refs[task.id].name}"
        for phase in phases
        for task in phase.tasks
        for blocker in task.blocked_by
    )
    return "\n".join(lines)


def _graph_node(ref: _TaskRef) -> str:
    return f'    {ref.name}["{_graph_label(f"{ref.name} {ref.title}")}"]'


def _graph_label(text: str) -> str:
    """A label that stays inside Mermaid's quotes: one line, cut short, no markup characters."""
    one_line = _WHITESPACE.sub(" ", text).strip()
    if len(one_line) > GRAPH_LABEL_LIMIT:
        one_line = one_line[: GRAPH_LABEL_LIMIT - 1].rstrip() + "…"
    return "".join(_GRAPH_ENTITIES.get(char, char) for char in one_line)
