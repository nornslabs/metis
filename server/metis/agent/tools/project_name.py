"""The Linear project name the export preview suggests: one short product name.

The model reads the project description (idea title, idea text, spec summary) and replies with
a name; ``clean_name`` checks it in code. A failed call, or a reply that is not a name, gives
``fallback_name`` (the first words of the idea title), so the export never fails because of the
suggestion.
"""

from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.constants import TAG_NOSTREAM

from metis.agent.prompts import load_prompt
from metis.agent.tools.export_project import cut, cut_at_word, spec_summary
from metis.core.logging import get_logger
from metis.core.ports import LLMProvider

PROJECT_NAME_PROMPT = "project_name"
# The cheap model the gate judges use; a name needs no more.
PROJECT_NAME_PURPOSE = "gate"
MAX_SUGGESTED_NAME_CHARS = 30
MAX_SUGGESTED_NAME_WORDS = 2
MAX_IDEA_TEXT_CHARS = 2_000
_QUOTES_AND_PUNCTUATION = " \t\"'`“”‘’.,;:!?-–—*#_()[]{}<>"
_WORD = re.compile(r"\S+")

logger = get_logger(__name__)


def clean_name(reply: str) -> str | None:
    """The name in a model ``reply``: trimmed, no surrounding quotes or punctuation, one line,
    1–2 words and at most ``MAX_SUGGESTED_NAME_CHARS`` characters. ``None`` when it is not one."""
    lines = [line for line in reply.strip().splitlines() if line.strip()]
    if len(lines) != 1:
        return None
    name = " ".join(lines[0].strip(_QUOTES_AND_PUNCTUATION).split())
    words = _WORD.findall(name)
    if not 1 <= len(words) <= MAX_SUGGESTED_NAME_WORDS or len(name) > MAX_SUGGESTED_NAME_CHARS:
        return None
    return name


def fallback_name(idea_title: str) -> str:
    """The first one or two words of ``idea_title``, cut to ``MAX_SUGGESTED_NAME_CHARS``."""
    words = _WORD.findall(idea_title)[:MAX_SUGGESTED_NAME_WORDS]
    return cut_at_word(" ".join(words), MAX_SUGGESTED_NAME_CHARS)


def project_description_text(*, idea_title: str, raw_text: str, spec_text: str) -> str:
    """What the naming model reads."""
    return (
        f"Idea title: {idea_title.strip()}\n\n"
        f"Idea text:\n{cut(raw_text, MAX_IDEA_TEXT_CHARS)}\n\n"
        f"Spec summary:\n{spec_summary(spec_text)}"
    )


async def suggest_project_name(
    model: LLMProvider | None, *, idea_title: str, raw_text: str, spec_text: str
) -> str:
    """One project name for the idea. Never raises: any failure gives ``fallback_name``."""
    fallback = fallback_name(idea_title)
    if model is None:
        return fallback
    try:
        reply = await model.ainvoke(
            [
                SystemMessage(content=load_prompt(PROJECT_NAME_PROMPT)),
                HumanMessage(
                    content=project_description_text(
                        idea_title=idea_title, raw_text=raw_text, spec_text=spec_text
                    )
                ),
            ],
            config={"tags": [TAG_NOSTREAM]},
        )
    except Exception as error:  # noqa: BLE001  (a naming failure must not stop the export)
        logger.warning("export.project_name_failed", error=type(error).__name__)
        return fallback
    name = clean_name(reply.text)
    if name is None:
        logger.warning("export.project_name_invalid")
        return fallback
    return name
