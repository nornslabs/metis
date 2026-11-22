"""The Architect's own tool: ``save_spec``, its structured output.

The model gives the idea's ``kind`` and one text per template section. The tool refuses a spec
with a missing or empty section, an unknown ``kind`` or a text that is too long, and the refusal
is a message the model can act on. The first refusal lets the model try again; the second closes
the tool, and the node then fails the run instead of storing a spec it cannot stand behind.
A valid spec is rendered to markdown and saved as the idea's next version (``source = agent``).
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from metis.agent.tools.research_kb import ResearchScope
from metis.core.logging import get_logger
from metis.modules import ideas
from metis.modules.ideas import (
    MAX_SPEC_LENGTH,
    IdeaKind,
    SpecSection,
    SpecSource,
    SpecVersion,
    render_spec_markdown,
)

SAVE_SPEC = "save_spec"
MAX_REFUSALS = 2
CLOSED = "Saving is closed: two attempts were refused. Stop."
SAVED = "Spec saved."

logger = get_logger(__name__)


class SpecRefused(Exception):
    """A call the model must fix; its text is what the model reads."""

    def __repr__(self) -> str:
        return str(self)


@dataclass
class SpecLedger:
    """What the loop did: the version it saved (``None`` yet) and how many calls were refused."""

    saved: SpecVersion | None = None
    refusals: int = 0


class SaveSpecArgs(BaseModel):
    """The Architect's structured output. Fields default to empty so that a missing one is a
    refusal the tool counts and the model can fix, not an error the loop never counts."""

    kind: str = Field(default="", description="`software` if the idea is software, else `other`.")
    problem: str = Field(default="", description="The problem, who has it and why it matters.")
    target_users: str = Field(default="", description="Who the product is for.")
    solution: str = Field(default="", description="What the product is and how it solves it.")
    key_features: str = Field(
        default="", description="Markdown list: MVP features first, then later ones."
    )
    non_goals: str = Field(default="", description="What the product will not do. Or `None.`")
    competitive_edge: str = Field(default="", description="Why it beats the alternatives.")
    success_metrics: str = Field(default="", description="How success will be measured.")
    risks: str = Field(default="", description="The main risks and how to reduce them.")
    open_questions: str = Field(default="", description="What is still unknown. Or `None.`")


def spec_tools(scope: ResearchScope, ledger: SpecLedger) -> list[BaseTool]:
    """The Architect's allow-list: ``save_spec`` only."""

    async def save_spec(**fields: str) -> str:
        if ledger.refusals >= MAX_REFUSALS:
            return CLOSED
        sections, kind, problem = _checked(fields)
        if problem is not None or kind is None:
            ledger.refusals += 1
            logger.warning("spec.save_refused", refusals=ledger.refusals)
            if ledger.refusals >= MAX_REFUSALS:
                return CLOSED
            raise SpecRefused("Nothing was saved. " + (problem or "Give a valid kind."))
        async with scope.session() as session:
            version = await ideas.save_spec_version(
                session,
                scope.workspace_id,
                scope.idea_id,
                ideas.NewSpecVersion(
                    content_md=render_spec_markdown(sections),
                    sections=sections,
                    source=SpecSource.AGENT,
                    run_id=scope.run_id,
                ),
            )
            await ideas.set_kind(session, scope.workspace_id, scope.idea_id, kind)
        ledger.saved = version
        return SAVED

    return [
        StructuredTool.from_function(
            coroutine=save_spec,
            name=SAVE_SPEC,
            description=(
                "Save the product spec: the idea's kind and one text per section. Every section "
                "needs text; write `None.` when a section has nothing."
            ),
            args_schema=SaveSpecArgs,
        )
    ]


def _checked(fields: dict[str, str]) -> tuple[dict[str, str], IdeaKind | None, str | None]:
    """The sections, the kind, and what is wrong (``None`` when the call is valid)."""
    kind = _kind(fields.get("kind", ""))
    sections = {
        section.value: str(fields.get(section.value, "")).strip() for section in SpecSection
    }
    missing = [key for key, text in sections.items() if not text]
    if missing:
        return sections, kind, f"These sections are empty: {', '.join(missing)}."
    if kind is None:
        return sections, kind, "`kind` must be `software` or `other`."
    if len(render_spec_markdown(sections)) > MAX_SPEC_LENGTH:
        return sections, kind, f"The spec is over {MAX_SPEC_LENGTH} characters; shorten it."
    return sections, kind, None


def _kind(value: str) -> IdeaKind | None:
    try:
        return IdeaKind(value.strip().casefold())
    except ValueError:
        return None
