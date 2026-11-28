"""Versioned prompt files: ``metis/prompts/<name>.v<N>.md``.

A prompt change is a new version file; existing versions are never edited, so a run can
be traced to the exact text it used. ``load_prompt`` returns the latest version unless
one is named, and raises ``PromptNotFoundError`` for an unknown name or version.

``load_specialist_prompt`` is the one way a specialist gets its prompt: the soul
(``soul.v<N>.md``, the voice shared by every specialist) followed by the specialist's own.
"""

from __future__ import annotations

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SOUL_PROMPT = "soul"
_VERSIONED = re.compile(r"^(?P<name>[a-z_]+)\.v(?P<version>[1-9][0-9]*)\.md$")


class PromptNotFoundError(LookupError):
    """No prompt file for the requested name or version (a code error, not a user error)."""


def load_prompt(name: str, version: int | None = None, *, directory: Path = PROMPTS_DIR) -> str:
    """The text of prompt ``name`` at ``version``, or at its latest version."""
    versions = _versions(name, directory)
    if not versions:
        raise PromptNotFoundError(f"No prompt named {name!r} in {directory}")
    chosen = max(versions) if version is None else version
    if chosen not in versions:
        raise PromptNotFoundError(
            f"Prompt {name!r} has no version {chosen}; available: {sorted(versions)}"
        )
    return versions[chosen].read_text(encoding="utf-8")


def load_specialist_prompt(name: str, version: int | None = None) -> str:
    """The soul followed by prompt ``name``: the text a specialist's model is given."""
    return f"{load_prompt(SOUL_PROMPT)}\n{load_prompt(name, version)}"


def _versions(name: str, directory: Path) -> dict[int, Path]:
    found: dict[int, Path] = {}
    for path in directory.glob(f"{name}.v*.md"):
        match = _VERSIONED.match(path.name)
        if match and match["name"] == name:
            found[int(match["version"])] = path
    return found
