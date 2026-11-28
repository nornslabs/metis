"""Read an HLD's markdown. The shape is written by the Architect's ``render_hld_markdown``: a
``## MVP components`` section whose components are ``###`` headings."""

from __future__ import annotations

COMPONENTS_HEADING = "mvp components"


def component_names(content_md: str) -> tuple[str, ...]:
    """The names of the HLD's MVP components, in order, each once (case-insensitive).

    Empty when the HLD has no ``## MVP components`` section. Code fences are skipped so a ``###``
    line inside one is not a component.
    """
    names: list[str] = []
    seen: set[str] = set()
    in_components = False
    in_fence = False
    for line in content_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith("## "):
            in_components = stripped[3:].strip().casefold() == COMPONENTS_HEADING
        elif in_components and stripped.startswith("### "):
            name = stripped[4:].strip()
            if name and name.casefold() not in seen:
                seen.add(name.casefold())
                names.append(name)
    return tuple(names)


def match_component(names: tuple[str, ...], wanted: str | None) -> str | None:
    """``wanted`` spelled as the HLD spells it (case-insensitive), or ``None`` when the HLD has
    no such component."""
    key = (wanted or "").strip().casefold()
    return next((name for name in names if name.casefold() == key), None) if key else None
