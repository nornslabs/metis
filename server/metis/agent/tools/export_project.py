"""The text the export puts in Linear for the project and its milestones.

Pure functions: the idea, spec, score and phases go in, names and Markdown descriptions come
out, cut to fixed limits. Nothing here calls Linear or reads secrets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

MAX_NAME_CHARS = 255
MAX_DESCRIPTION_CHARS = 4_000
MAX_SPEC_SUMMARY_CHARS = 600
ELLIPSIS = "…"


@dataclass(frozen=True)
class ProjectScore:
    """The idea's latest score as the project description shows it."""

    total: int
    band: str


def cut(text: str, limit: int) -> str:
    """``text`` stripped and cut to ``limit`` characters, with an ellipsis when it was cut."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - len(ELLIPSIS)].rstrip() + ELLIPSIS


def idea_url(web_base_url: str, idea_id: UUID) -> str:
    """Where the idea lives in the Metis web app."""
    return f"{web_base_url.rstrip('/')}/ideas/{idea_id}"


def project_name(idea_title: str) -> str:
    return cut(idea_title, MAX_NAME_CHARS)


def spec_summary(spec_text: str) -> str:
    """The spec's prose on one line (headings dropped), cut for the project description."""
    lines = [line.strip() for line in spec_text.splitlines()]
    prose = " ".join(line for line in lines if line and not line.startswith("#"))
    return cut(prose, MAX_SPEC_SUMMARY_CHARS)


def project_description(
    *, url: str, spec_text: str, score: ProjectScore | None, plan_version: int
) -> str:
    """Markdown for the project: a link back to Metis, the spec summary, the score and band,
    and the plan version the export was made from."""
    parts = [f"Planned in [Metis]({url})."]
    summary = spec_summary(spec_text)
    if summary:
        parts.append(f"**Spec**\n\n{summary}")
    if score is not None:
        parts.append(f"**Score**: {score.total}/100 ({score.band})")
    parts.append(f"Plan version {plan_version}.")
    return cut("\n\n".join(parts), MAX_DESCRIPTION_CHARS)


def milestone_name(position: int, phase_name: str) -> str:
    """``Phase N — <name>`` where N is the phase's 1-based place in the plan."""
    return cut(f"Phase {position + 1} — {phase_name.strip()}", MAX_NAME_CHARS)


def milestone_description(goal: str, exit_criteria: str) -> str:
    """Markdown for a milestone: the phase goal and its exit criteria."""
    return cut(
        f"**Goal**\n\n{goal.strip()}\n\n**Exit criteria**\n\n{exit_criteria.strip()}",
        MAX_DESCRIPTION_CHARS,
    )
