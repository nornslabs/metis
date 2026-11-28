"""The Architect's HLD tools: ``save_hld`` (its structured output) and ``ask_build_language``.

The HLD is a blueprint of a software idea's MVP: the build language and stack, the components
with their purpose and responsibilities, how they connect and the functional requirements. It
holds no code and no low-level detail (no schemas, signatures or file layouts); a text with a
code fence is refused. ``save_hld`` follows the ``save_spec`` rules: a refusal is a message the
model can act on, the first lets it try again and the second closes the tool.

``ask_build_language`` is the one question the Architect may ask, and only when the idea text and
the interview name no language or stack. It pauses on the ``question`` interrupt (without the
Interviewer's progress counter), saves the answer as an interview turn and asks at most once.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from metis.agent.tools.question_options import OptionArgs, check_options, question_payload
from metis.agent.tools.research_kb import ResearchScope
from metis.core.logging import get_logger
from metis.modules import ideas
from metis.modules.ideas import (
    MAX_HLD_LENGTH,
    InterviewTopic,
    NewSpecHld,
    SpecHld,
    SpecVersion,
    TurnSource,
    spec_hash,
)

SAVE_HLD = "save_hld"
ASK_BUILD_LANGUAGE = "ask_build_language"
BUILD_LANGUAGE_QUESTION = "What language or stack will you build this in?"
MAX_REFUSALS = 2
MIN_COMPONENTS = 1
MAX_COMPONENTS = 12
CODE_FENCE = "```"
CLOSED = "Saving is closed: two attempts were refused. Stop."
SAVED = "HLD saved."
ASKED_ALREADY = "The user was already asked. Their answer: {answer}. Use it; do not ask again."

logger = get_logger(__name__)


class HldRefused(Exception):
    """A call the model must fix; its text is what the model reads."""

    def __repr__(self) -> str:
        return str(self)


@dataclass
class HldLedger:
    """What the loop did: the HLD it saved (``None`` yet), the user's answer to the language
    question (``None`` if it was not asked) and how many ``save_hld`` calls were refused."""

    saved: SpecHld | None = None
    language_answer: str | None = None
    refusals: int = 0


class ComponentArg(BaseModel):
    name: str = Field(default="", description="Short component name, e.g. `Auth`.")
    purpose: str = Field(default="", description="One sentence: what the component is for.")
    responsibilities: str = Field(
        default="", description="Markdown list of what the component is responsible for."
    )


class SaveHldArgs(BaseModel):
    """The Architect's HLD. Fields default to empty so that a missing one is a refusal the tool
    counts and the model can fix, not an error the loop never counts."""

    build_language: str = Field(
        default="", description="The language or stack the product is built in, e.g. `Python`."
    )
    overview: str = Field(default="", description="What the system is and the main idea behind it.")
    stack: str = Field(
        default="", description="The main technologies of the stack, as a short markdown list."
    )
    components: list[ComponentArg] = Field(
        default_factory=list, description=f"The MVP broken into {MIN_COMPONENTS}-{MAX_COMPONENTS}."
    )
    connections: str = Field(
        default="", description="How the components connect and what data moves between them."
    )
    functional_requirements: str = Field(
        default="", description="Markdown list of what the MVP must do."
    )


class AskBuildLanguageArgs(BaseModel):
    options: list[OptionArgs] = Field(
        default_factory=list,
        description="3 or 4 languages or stacks that fit this idea; the user may also type one.",
    )


def render_hld_markdown(args: SaveHldArgs) -> str:
    """The HLD as markdown: overview, build language and stack, components, connections,
    functional requirements."""
    components = "\n\n".join(
        f"### {c.name.strip()}\n\n**Purpose:** {c.purpose.strip()}\n\n"
        f"**Responsibilities:**\n{c.responsibilities.strip()}"
        for c in args.components
    )
    return (
        f"## Overview\n\n{args.overview.strip()}\n\n"
        f"## Build language and stack\n\n**Language:** {args.build_language.strip()}\n\n"
        f"{args.stack.strip()}\n\n"
        f"## MVP components\n\n{components}\n\n"
        f"## How the components connect\n\n{args.connections.strip()}\n\n"
        f"## Functional requirements\n\n{args.functional_requirements.strip()}"
    )


def hld_tools(
    scope: ResearchScope, ledger: HldLedger, spec: SpecVersion, *, may_ask: bool
) -> list[BaseTool]:
    """The HLD loop's allow-list: ``save_hld``, plus ``ask_build_language`` when the language is
    not known yet."""
    tools = [_save_hld(scope, ledger, spec)]
    if may_ask:
        tools.append(_ask_build_language(scope, ledger))
    return tools


def _save_hld(scope: ResearchScope, ledger: HldLedger, spec: SpecVersion) -> BaseTool:
    async def save_hld(
        build_language: str = "",
        overview: str = "",
        stack: str = "",
        components: list[ComponentArg] | None = None,
        connections: str = "",
        functional_requirements: str = "",
    ) -> str:
        if ledger.refusals >= MAX_REFUSALS:
            return CLOSED
        args = SaveHldArgs(
            build_language=build_language,
            overview=overview,
            stack=stack,
            components=components or [],
            connections=connections,
            functional_requirements=functional_requirements,
        )
        if (problem := _problem(args)) is not None:
            ledger.refusals += 1
            logger.warning("hld.save_refused", refusals=ledger.refusals)
            if ledger.refusals >= MAX_REFUSALS:
                return CLOSED
            raise HldRefused("Nothing was saved. " + problem)
        async with scope.session() as session:
            ledger.saved = await ideas.save_spec_hld(
                session,
                scope.workspace_id,
                scope.idea_id,
                NewSpecHld(
                    spec_version_number=spec.number,
                    spec_hash=spec_hash(spec.content_md),
                    build_language=args.build_language,
                    content_md=render_hld_markdown(args),
                ),
            )
        return SAVED

    return StructuredTool.from_function(
        coroutine=save_hld,
        name=SAVE_HLD,
        description=(
            "Save the high-level design: the build language, the overview, the stack, the MVP "
            "components, how they connect and the functional requirements. Blueprint only: no "
            "code and no low-level detail."
        ),
        args_schema=SaveHldArgs,
    )


def _ask_build_language(scope: ResearchScope, ledger: HldLedger) -> BaseTool:
    async def ask_build_language(options: list[OptionArgs] | None = None) -> str:
        if ledger.language_answer is not None:
            return ASKED_ALREADY.format(answer=ledger.language_answer)
        proposed = options or []
        if proposed and (problem := check_options(proposed, multi=False)):
            return problem
        payload = question_payload(
            BUILD_LANGUAGE_QUESTION, proposed, multi=False, allow_free_text=True, index=1, total=1
        )
        # The Interviewer's "Question n of up to m" counter does not apply to this one question.
        answer = str(interrupt({k: v for k, v in payload.items() if k not in {"index", "total"}}))
        ledger.language_answer = answer
        await _record_answer(scope, answer)
        return f"The user will build it in: {answer}"

    return StructuredTool.from_function(
        coroutine=ask_build_language,
        name=ASK_BUILD_LANGUAGE,
        description=(
            "Ask the user which language or stack they will build this in and wait for the "
            "answer. Use it once, and only when the idea text and the interview name none."
        ),
        args_schema=AskBuildLanguageArgs,
    )


async def _record_answer(scope: ResearchScope, answer: str) -> None:
    """Keep the answer in the interview so it is never asked again (re-run safe)."""
    async with scope.session() as session:
        turns = await ideas.list_turns(session, scope.workspace_id, scope.idea_id)
        if any(
            t.run_id == scope.run_id
            and t.source is TurnSource.NOTED
            and t.question == BUILD_LANGUAGE_QUESTION
            for t in turns
        ):
            return
        await ideas.save_interview_turn(
            session,
            scope.workspace_id,
            scope.idea_id,
            scope.run_id,
            InterviewTopic.OTHER,
            BUILD_LANGUAGE_QUESTION,
            answer,
        )


def _problem(args: SaveHldArgs) -> str | None:
    """What is wrong with the HLD, or ``None`` when it follows the rules."""
    top = {
        "build_language": args.build_language,
        "overview": args.overview,
        "stack": args.stack,
        "connections": args.connections,
        "functional_requirements": args.functional_requirements,
    }
    if empty := [name for name, text in top.items() if not text.strip()]:
        return f"These fields are empty: {', '.join(empty)}."
    if not MIN_COMPONENTS <= len(args.components) <= MAX_COMPONENTS:
        return f"Give {MIN_COMPONENTS} to {MAX_COMPONENTS} MVP components."
    for component in args.components:
        if not (component.name.strip() and component.purpose.strip()):
            return "Every component needs a name and a purpose."
        if not component.responsibilities.strip():
            return f"Component `{component.name}` has no responsibilities."
    text = render_hld_markdown(args)
    if CODE_FENCE in text:
        return "The HLD is a blueprint: remove code blocks and describe the design in words."
    if len(text) > MAX_HLD_LENGTH:
        return f"The HLD is over {MAX_HLD_LENGTH} characters; shorten it."
    return None
