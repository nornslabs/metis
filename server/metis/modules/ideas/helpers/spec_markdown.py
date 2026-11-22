"""Turn a spec's sections into markdown and back, and compare two versions section by section.

The template's sections are ``## <Heading>`` blocks. Text a user wrote under a heading the
template does not know is kept under a slug key, so parsing never drops what they wrote.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from metis.modules.ideas.dto.spec import (
    NONE_TEXT,
    SECTION_HEADINGS,
    DiffStatus,
    SectionDiff,
    SpecSection,
)

_HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*#*[ \t]*$")
_NON_SLUG = re.compile(r"[^a-z0-9]+")
_KEY_BY_HEADING = {
    heading.casefold(): section.value for section, heading in SECTION_HEADINGS.items()
}
_TEMPLATE_KEYS = tuple(section.value for section in SpecSection)


def render_markdown(sections: Mapping[str, str]) -> str:
    """The spec as markdown: template sections in order (empty ones say "None."), then others."""
    blocks = [
        _block(SECTION_HEADINGS[SpecSection(key)], sections.get(key, "")) for key in _TEMPLATE_KEYS
    ]
    extra = [key for key in sections if key not in _TEMPLATE_KEYS]
    blocks += [_block(_title(key), sections[key]) for key in extra]
    return "\n\n".join(blocks) + "\n"


def parse_sections(content_md: str) -> dict[str, str]:
    """The text under each ``## `` heading: template headings by key, others by slug."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in content_md.splitlines():
        match = _HEADING.match(line)
        if match is not None:
            heading = match.group(1)
            current = _KEY_BY_HEADING.get(heading.casefold()) or _slug(heading)
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def diff_sections(a: Mapping[str, str], b: Mapping[str, str]) -> list[SectionDiff]:
    """Per section (template order, then the others): unchanged, changed, added or removed."""
    keys = [*_TEMPLATE_KEYS, *(k for k in [*a, *b] if k not in _TEMPLATE_KEYS)]
    seen: set[str] = set()
    result: list[SectionDiff] = []
    for key in keys:
        if key in seen or (key not in a and key not in b):
            continue
        seen.add(key)
        result.append(_compare(key, a.get(key), b.get(key)))
    return result


def _compare(key: str, a_text: str | None, b_text: str | None) -> SectionDiff:
    if a_text is None:
        status = DiffStatus.ADDED
    elif b_text is None:
        status = DiffStatus.REMOVED
    elif a_text.strip() == b_text.strip():
        status = DiffStatus.UNCHANGED
    else:
        status = DiffStatus.CHANGED
    return SectionDiff(section=key, status=status, a_text=a_text, b_text=b_text)


def _block(heading: str, text: str) -> str:
    return f"## {heading}\n\n{text.strip() or NONE_TEXT}"


def _slug(heading: str) -> str:
    return _NON_SLUG.sub("_", heading.casefold()).strip("_") or "section"


def _title(key: str) -> str:
    return key.replace("_", " ").capitalize()
