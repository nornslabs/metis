"""The issue brief: the structure of a task description and how it is fitted into Linear's limit.

A brief is Markdown with ``##`` sections in a fixed order: Goal, Context, Requirements,
Out of scope, Acceptance criteria, Dependencies, and an optional Agent notes. Pure functions:
text goes in, text or a list of missing sections comes out. Nothing here calls Linear.

A description with none of the known sections (a plan saved before briefs existed) is free
text: it is only cut to the limit, never refused.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from metis.agent.tools.export_project import cut

GOAL = "Goal"
CONTEXT = "Context"
REQUIREMENTS = "Requirements"
OUT_OF_SCOPE = "Out of scope"
ACCEPTANCE = "Acceptance criteria"
DEPENDENCIES = "Dependencies"
AGENT_NOTES = "Agent notes"

SECTIONS = (GOAL, CONTEXT, REQUIREMENTS, OUT_OF_SCOPE, ACCEPTANCE, DEPENDENCIES, AGENT_NOTES)
REQUIRED_SECTIONS = (GOAL, REQUIREMENTS, ACCEPTANCE)

# What is cut, in this order, when a brief is too long. Agent notes go before everything else.
# Dependencies come before Requirements: Linear's blocked-by links already carry them.
_DROP_ORDER = (CONTEXT, DEPENDENCIES)
_SECTION_START = re.compile(r"(?m)^(?=##[ \t]+\S)")
_SECTION_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class Section:
    """One chunk of a description. ``name`` is the casefolded heading, empty for text before the
    first heading; ``text`` is the whole chunk, heading line included."""

    name: str
    text: str

    @property
    def body(self) -> str:
        """The chunk without its heading line."""
        return self.text.split("\n", 1)[1].strip() if "\n" in self.text else ""


def heading(name: str) -> str:
    """The Markdown heading line of section ``name``, e.g. ``## Goal``."""
    return f"## {name}"


def parse_sections(description: str) -> tuple[Section, ...]:
    """The description split at its ``##`` headings, in order. Empty chunks are dropped."""
    chunks = (chunk.strip() for chunk in _SECTION_START.split(description))
    return tuple(Section(name=_heading_name(text), text=text) for text in chunks if text)


def missing_sections(description: str) -> tuple[str, ...]:
    """The required sections the description lacks or leaves empty, in brief order."""
    filled = {s.name for s in parse_sections(description) if s.body}
    return tuple(name for name in REQUIRED_SECTIONS if _key(name) not in filled)


def fit_brief(description: str, limit: int) -> str:
    """The brief within ``limit`` characters.

    What goes first when it is too long: the Agent notes, then Context, then Dependencies, then
    the tail of Requirements. Goal and Acceptance criteria are kept whole unless they alone
    exceed ``limit`` (the last resort is a plain cut). Free text is only cut.
    """
    sections = parse_sections(description)
    if not any(section.name in _KNOWN for section in sections):
        return cut(description, limit)
    notes = tuple(_collapsible(s) for s in sections if s.name == _key(AGENT_NOTES) and s.body)
    kept = tuple(s for s in sections if s.name != _key(AGENT_NOTES))
    if len(with_notes := _join(kept, notes)) <= limit:
        return with_notes
    for dropped in (None, *_DROP_ORDER):
        kept = tuple(s for s in kept if s.name != (dropped and _key(dropped)))
        if len(text := _join(kept)) <= limit:
            return text
    return _shrink_requirements(kept, limit)


def _shrink_requirements(sections: tuple[Section, ...], limit: int) -> str:
    whole = _join(sections)
    if len(whole) <= limit:
        return whole
    requirements = _key(REQUIREMENTS)
    others = _join(tuple(s for s in sections if s.name != requirements))
    room = limit - len(others) - len(_SECTION_SEPARATOR)
    shrunk = tuple(
        Section(name=s.name, text=cut(s.text, max(room, 0))) if s.name == requirements else s
        for s in sections
    )
    return cut(_join(shrunk), limit)


def _join(sections: tuple[Section, ...], extra: tuple[str, ...] = ()) -> str:
    return _SECTION_SEPARATOR.join((*(s.text for s in sections), *extra))


def _collapsible(section: Section) -> str:
    """Linear's collapsible block for the Agent notes: ``>>> Title`` ... ``>>>``."""
    return f">>> {AGENT_NOTES}\n\n{section.body}\n\n>>>"


def _heading_name(text: str) -> str:
    first_line = text.split("\n", 1)[0]
    if not first_line.startswith("##"):
        return ""
    return first_line.lstrip("#").strip().rstrip(":").strip().casefold()


def _key(section: str) -> str:
    """The form a section name is compared in: headings match ignoring case."""
    return section.casefold()


_KNOWN = frozenset(_key(name) for name in SECTIONS)
